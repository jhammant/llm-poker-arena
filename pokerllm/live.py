"""Turn engine events into a 'live table' JSON snapshot for the broadcast page.

Carries: the current table (hole cards, board, pot, last action), a streaming
"thinking" buffer (the acting model's tokens as they arrive), a rolling feed,
the running match score, the full game schedule (done/live/upcoming), a money
leaderboard, and an archive of recent completed hands for replay.
"""
from __future__ import annotations

import datetime
import json
import os
import time


class LiveBroadcast:
    def __init__(self, path: str):
        self.path = path
        self._score = [0, 0]
        self._last_stream_write = 0.0
        self._recent: list = []   # last completed hands (for replay)
        self._cur: dict | None = None  # current hand's event accumulator
        self.state: dict = {
            "status": "running", "match": None, "match_index": 0, "total_matches": 0,
            "hand_no": 0, "names": ["", ""], "button": 0, "hole": ["", ""], "board": "-",
            "street": "", "pot": 0, "stacks": [0, 0], "start_stack": 0, "bb": 2,
            "last_action": None, "feed": [], "result": None, "score": [0, 0],
            "leaderboard": [], "schedule": [], "thinking": None, "recent_hands": [],
            "talk": None, "updated": "",
        }

    # -------------------------------------------------------------- schedule
    def set_schedule(self, pairs: list, start_stack: int, bb: int) -> None:
        self.state["schedule"] = [{"a": p["a"], "b": p["b"], "status": "upcoming",
                                   "chips_a": None} for p in pairs]
        self.state["total_matches"] = len(pairs)
        self.state["start_stack"] = start_stack
        self.state["bb"] = bb
        self._write()

    def set_match(self, a: str, b: str, index: int, total: int, leaderboard: list, start_stack: int) -> None:
        self._score = [0, 0]
        self.state.update({
            "match": {"a": a, "b": b}, "names": [a, b], "match_index": index,
            "total_matches": total, "leaderboard": leaderboard, "score": [0, 0],
            "result": None, "feed": [], "start_stack": start_stack,
            "stacks": [start_stack, start_stack], "hand_no": 0, "thinking": None,
        })
        sch = self.state["schedule"]
        if 1 <= index <= len(sch):
            sch[index - 1]["status"] = "live"
        self._write()

    def complete_match(self, index: int, chips_a: int, leaderboard: list) -> None:
        sch = self.state["schedule"]
        if 1 <= index <= len(sch):
            sch[index - 1]["status"] = "done"
            sch[index - 1]["chips_a"] = chips_a
        self.state["leaderboard"] = leaderboard
        self.state["thinking"] = None
        self._write()

    # --------------------------------------------------------- token stream
    def stream_token(self, seat: int, thinking: str, answer: str) -> None:
        disp = thinking or ""
        if answer:
            disp = disp + ("\n" if disp else "") + answer
        self.state["thinking"] = {"seat": seat, "text": disp.strip()[-1400:]}
        now = time.time()
        if now - self._last_stream_write >= 0.25:  # throttle file writes
            self._last_stream_write = now
            self._write()

    # --------------------------------------------------------------- events
    def on_event(self, ev: dict) -> None:
        s = self.state
        names = s["names"]
        t = ev.get("type")
        if t == "hand_start":
            s["hand_no"] += 1
            s["button"] = ev["button"]
            s["hole"] = ev["holes"]
            s["board"] = "-"
            s["street"] = "preflop"
            s["pot"] = ev["sb"] + ev["bb"]
            s["last_action"] = None
            s["result"] = None
            s["thinking"] = None
            s["talk"] = None
            s["feed"].append({"kind": "hand", "text": f"— hand {s['hand_no']} (dealer: {names[ev['button']]}) —"})
            self._cur = {"hand_no": s["hand_no"], "names": list(names),
                         "button": ev["button"], "events": [dict(ev)]}
        elif t == "board":
            s["board"] = ev["board"]
            s["street"] = ev["street"]
            s["feed"].append({"kind": "board", "text": f"{ev['street']}: {ev['board']}"})
            if self._cur:
                self._cur["events"].append(dict(ev))
        elif t == "action":
            seat = ev["seat"]
            s["pot"] = ev["pot"]
            s["thinking"] = None
            if "stacks" in ev:
                s["stacks"] = ev["stacks"]
            s["last_action"] = {"seat": seat, "action": ev["action"],
                                "amount": ev["amount"], "note": ev.get("note", "")}
            s["feed"].append({"kind": "action", "seat": seat, "name": names[seat],
                              "action": ev["action"], "amount": ev["amount"], "note": ev.get("note", "")})
            if ev.get("talk"):
                s["talk"] = {"seat": seat, "name": names[seat], "msg": ev["talk"]}
                s["feed"].append({"kind": "talk", "seat": seat, "name": names[seat], "msg": ev["talk"]})
            if self._cur:
                # dict(ev) copies the action event verbatim, so any "talk" string
                # is carried into recent_hands automatically.
                self._cur["events"].append(dict(ev))
        elif t == "result":
            d = ev["deltas"]
            self._score[0] += d[0]
            self._score[1] += d[1]
            s["score"] = list(self._score)
            if ev.get("showdown"):
                s["hole"] = ev.get("holes", s["hole"])
            s["board"] = ev.get("board", s["board"])
            s["result"] = {"note": ev.get("note", ""), "deltas": d, "showdown": ev.get("showdown", False)}
            s["feed"].append({"kind": "result", "text": "▶ " + ev.get("note", "")})
            if self._cur:
                self._cur["events"].append(dict(ev))
                self._cur["winner"] = 0 if d[0] > d[1] else (1 if d[1] > d[0] else -1)
                self._recent.append(self._cur)
                self._recent = self._recent[-12:]
                s["recent_hands"] = self._recent
                self._cur = None
        s["feed"] = s["feed"][-18:]
        self._write()

    def finish(self) -> None:
        self.state["status"] = "complete"
        self.state["thinking"] = None
        self._write()

    def _write(self) -> None:
        self.state["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)  # atomic — readers never see a partial file
