"""FastAPI dashboard: watch a heads-up session play out live (cards, bets, pot)
with each player's reasoning shown per decision, plus a leaderboard from saved runs.

The engine + session loop are synchronous, so a session runs in a worker thread
and pushes events onto an asyncio queue consumed by the WebSocket. A small per-event
delay paces free (instant) players so the table is watchable; LLM latency paces
itself, so set delay=0 for real models.
"""
from __future__ import annotations

import asyncio
import glob
import json
import random
import threading
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from ..cards import shuffled_deck
from ..engine import play_hand
from ..players.heuristic import HeuristicPlayer
from ..players.random_player import RandomPlayer

STATIC = Path(__file__).parent / "static"
app = FastAPI(title="pokerllm dashboard")


def _make_player(name: str):
    if name == "heuristic":
        return HeuristicPlayer("heuristic")
    if name == "random":
        return RandomPlayer("random", seed=random.randint(0, 99999))
    from ..config import load_config, make_player  # LLM (needs a running provider)

    return make_player(load_config(), name)


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse((STATIC / "index.html").read_text())


@app.get("/api/players")
async def players() -> dict:
    models: list[str] = []
    try:
        from ..config import load_config

        models = [p["name"] for p in load_config().get("players", [])]
    except Exception:
        pass
    return {"builtin": ["heuristic", "random"], "models": models}


@app.get("/api/runs")
async def runs() -> dict:
    out = []
    for path in sorted(glob.glob("runs/*.json"), reverse=True)[:20]:
        try:
            with open(path) as f:
                data = json.load(f)
            out.append({"path": path, "created": data.get("created"),
                        "config": data.get("config"), "ratings": data.get("ratings"),
                        "reference": data.get("reference", {})})
        except Exception:
            pass
    return {"runs": out}


def _run_session(p0, p1, hands, stack, sb, bb, delay, emit) -> None:
    rng = random.Random()
    score = [0, 0]
    emit({"type": "init", "names": [p0.name, p1.name], "stack": stack, "bb": bb, "hands": hands})

    def paced(ev: dict) -> None:
        emit(ev)
        if delay:
            time.sleep(delay)

    for h in range(hands):
        button = h % 2
        deck = shuffled_deck(rng)
        try:
            res = play_hand([p0, p1], [stack, stack], button, bb, sb, deck, on_event=paced)
        except Exception as e:  # never kill the stream
            emit({"type": "error", "error": repr(e)})
            break
        score[0] += res.deltas[0]
        score[1] += res.deltas[1]
        emit({"type": "score", "score": score, "hand": h + 1, "hands": hands})
        if delay:
            time.sleep(delay * 1.5)
    emit({"type": "session_end", "score": score})


@app.websocket("/ws/play")
async def ws_play(ws: WebSocket) -> None:
    await ws.accept()
    qp = ws.query_params
    p0name, p1name = qp.get("p0", "heuristic"), qp.get("p1", "random")
    hands = int(qp.get("hands", "15"))
    stack, sb, bb = int(qp.get("stack", "200")), int(qp.get("sb", "1")), int(qp.get("bb", "2"))
    delay = float(qp.get("delay", "0.6"))
    try:
        p0, p1 = _make_player(p0name), _make_player(p1name)
    except Exception as e:
        await ws.send_json({"type": "error", "error": f"player setup failed: {e!r}"})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    q: asyncio.Queue = asyncio.Queue()

    def emit(ev: dict) -> None:  # called from the worker thread
        loop.call_soon_threadsafe(q.put_nowait, ev)

    threading.Thread(target=_run_session, args=(p0, p1, hands, stack, sb, bb, delay, emit),
                     daemon=True).start()
    try:
        while True:
            ev = await q.get()
            await ws.send_json(ev)
            if ev["type"] == "session_end":
                break
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass
