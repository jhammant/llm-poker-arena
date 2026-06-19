"""Turn engine events into a 'live table' JSON snapshot for the broadcast page.

The bake-off feeds each match's engine events through LiveBroadcast; it keeps the
current table state (hole cards, board, pot, last action + reasoning, a rolling
feed, running match score, and the current leaderboard) and writes it atomically
to a file. A host-side pusher ships that file to the hosted viewer every ~1s.
"""
from __future__ import annotations

import datetime
import json
import os


class LiveBroadcast:
    def __init__(self, path: str):
        self.path = path
        self._score = [0, 0]
        self.state: dict = {
            "status": "running",
            "match": None,
            "match_index": 0,
            "total_matches": 0,
            "hand_no": 0,
            "names": ["", ""],
            "button": 0,
            "hole": ["", ""],
            "board": "-",
            "street": "",
            "pot": 0,
            "stacks": [0, 0],
            "start_stack": 0,
            "last_action": None,
            "feed": [],
            "result": None,
            "score": [0, 0],
            "leaderboard": [],
            "updated": "",
        }

    def set_match(self, a: str, b: str, index: int, total: int, leaderboard: list, start_stack: int) -> None:
        self._score = [0, 0]
        self.state.update({
            "match": {"a": a, "b": b}, "names": [a, b], "match_index": index,
            "total_matches": total, "leaderboard": leaderboard, "score": [0, 0],
            "result": None, "feed": [], "start_stack": start_stack,
            "stacks": [start_stack, start_stack], "hand_no": 0,
        })
        self._write()

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
            s["feed"].append({"kind": "hand", "text": f"— hand {s['hand_no']} (dealer: {names[ev['button']]}) —"})
        elif t == "board":
            s["board"] = ev["board"]
            s["street"] = ev["street"]
            s["feed"].append({"kind": "board", "text": f"{ev['street']}: {ev['board']}"})
        elif t == "action":
            seat = ev["seat"]
            s["pot"] = ev["pot"]
            if "stacks" in ev:
                s["stacks"] = ev["stacks"]
            s["last_action"] = {"seat": seat, "action": ev["action"],
                                "amount": ev["amount"], "note": ev.get("note", "")}
            s["feed"].append({"kind": "action", "seat": seat, "name": names[seat],
                              "action": ev["action"], "amount": ev["amount"], "note": ev.get("note", "")})
        elif t == "result":
            d = ev["deltas"]
            self._score[0] += d[0]
            self._score[1] += d[1]
            s["score"] = list(self._score)
            if ev.get("showdown"):
                s["hole"] = ev.get("holes", s["hole"])
            s["board"] = ev.get("board", s["board"])
            s["result"] = {"note": ev.get("note", ""), "deltas": d,
                           "showdown": ev.get("showdown", False)}
            s["feed"].append({"kind": "result", "text": "▶ " + ev.get("note", "")})
        s["feed"] = s["feed"][-18:]
        self._write()

    def finish(self) -> None:
        self.state["status"] = "complete"
        self._write()

    def _write(self) -> None:
        self.state["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.state, f)
        os.replace(tmp, self.path)  # atomic — readers never see a partial file
