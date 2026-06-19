"""Bake-off arena.

Runs a round-robin (and an optional cheap gauntlet vs the built-in heuristic)
among a list of competitors, accumulating Elo + BB/100, latency/token usage, and
per-match results. Everything is written to a JSON file so reports can be
regenerated without replaying games.

A competitor's model can be:
  * an LLM player name from config/models.yaml, or
  * the built-in "heuristic" / "random" players (free, instant skill anchors).

"Tuition" = the strategy corpus injected into the model's system prompt, so a
model can be entered twice — plain and "+tuition" — for a clean A/B.
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import random
import time
from dataclasses import dataclass

from . import report
from .config import load_config, make_player
from .match import play_session
from .players.heuristic import HeuristicPlayer
from .players.llm_player import LLMPlayer
from .players.random_player import RandomPlayer
from .rating import Elo, bb_per_100, bootstrap_ci

STRATEGY_DIR = "strategy_docs"
CHEATSHEET = "tuition/cheatsheet.md"
TUITION_CHAR_CAP = 16000
ANCHORS = {"heuristic", "random", "perfect"}


@dataclass
class Competitor:
    label: str  # unique display name, e.g. "gpt-oss-20b+tuition"
    model: str  # config player name, or "heuristic" / "random"
    tuition: bool = False


def load_tuition(mode: str = "full", directory: str = STRATEGY_DIR) -> str | None:
    """Build the tuition block.

    mode="lite": the condensed cheat-sheet (small, fast, fair test of guidance).
    mode="full": the whole strategy corpus concatenated (large; may degrade
                 small models — see the directional findings).
    """
    if mode == "lite":
        try:
            with open(CHEATSHEET) as f:
                return f.read().strip()[:TUITION_CHAR_CAP]
        except FileNotFoundError:
            return None
    files = sorted(glob.glob(os.path.join(directory, "*.md")))
    if not files:
        return None
    chunks = [open(p).read().strip() for p in files]
    return "\n\n---\n\n".join(chunks)[:TUITION_CHAR_CAP]


def _build_player(cfg: dict, comp: Competitor, tuition_text: str | None):
    if comp.model == "heuristic":
        p = HeuristicPlayer(comp.label)
    elif comp.model == "random":
        p = RandomPlayer(comp.label, seed=hash(comp.label) % 10000)
    elif comp.model == "perfect":
        from .equity import PerfectishPlayer  # near-optimal equity baseline
        p = PerfectishPlayer(comp.label)
    else:
        extra = tuition_text if comp.tuition else None
        p = make_player(cfg, comp.model, system_extra=extra)
        p.name = comp.label
    return p


class _SoundnessAnalyzer:
    """Per-decision 'distance from perfect play' from the event stream.

    Uses equity.analyze_decision (Monte-Carlo equity vs a random hand + pot odds)
    to flag clear EV mistakes. A no-op if equity.py isn't present yet.
    """

    def __init__(self):
        try:
            from .equity import analyze_decision
            self._analyze = analyze_decision
        except Exception:
            self._analyze = None
        from treys import Card
        self._Card = Card
        self.stats: dict[str, dict] = {}
        self._labels = ["", ""]
        self._holes = ["", ""]
        self._board: list[int] = []

    def set_labels(self, labels):
        self._labels = labels

    def _parse(self, s):
        if not s or s == "-":
            return []
        return [self._Card.new(t) for t in s.split()]

    def on_event(self, ev: dict) -> None:
        if self._analyze is None:
            return
        t = ev.get("type")
        if t == "hand_start":
            self._holes = ev["holes"]
            self._board = []
        elif t == "board":
            self._board = self._parse(ev["board"])
        elif t == "action":
            seat = ev["seat"]
            label = self._labels[seat] if seat < len(self._labels) else None
            if not label:
                return
            hole = self._parse(self._holes[seat]) if seat < len(self._holes) else []
            if len(hole) != 2:
                return
            try:
                r = self._analyze(hole, self._board, ev.get("to_call", 0), ev.get("pot", 0),
                                  ev.get("action", ""), ev.get("amount", 0), ev.get("to_call", 0) == 0)
            except Exception:
                return
            st = self.stats.setdefault(label, {"decisions": 0, "blunders": 0, "ev_lost": 0.0})
            st["decisions"] += 1
            if r.get("blunder"):
                st["blunders"] += 1
            st["ev_lost"] += float(r.get("ev_lost", 0.0) or 0.0)

    def summary(self, bb: int, bb_deltas: dict) -> dict:
        out = {}
        for label, st in self.stats.items():
            dec = max(st["decisions"], 1)
            hands = max(len(bb_deltas.get(label, [])), 1)
            out[label] = {
                "decisions": st["decisions"],
                "blunders": st["blunders"],
                "blunder_rate": round(100.0 * st["blunders"] / dec, 1),
                "ev_sound_pct": round(100.0 * (1 - st["blunders"] / dec), 1),
                "ev_lost_bb100": round((st["ev_lost"] / bb) / hands * 100, 1),
            }
        return out


def _usage_of(player) -> dict:
    u = getattr(player, "usage", None)
    if u is None:
        return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                "avg_latency_s": 0.0, "parse_failures": 0, "errors": 0, "llm": False}
    return {
        "calls": u.calls,
        "prompt_tokens": u.prompt_tokens,
        "completion_tokens": u.completion_tokens,
        "avg_latency_s": round(u.avg_latency_s, 3),
        "parse_failures": u.parse_failures,
        "errors": u.errors,
        "llm": True,
    }


def run_bakeoff(
    competitors: list[Competitor],
    hands: int,
    stack: int = 200,
    sb: int = 1,
    bb: int = 2,
    seed: int = 42,
    duplicate: bool = False,
    reference_hands: int = 0,
    out_path: str | None = None,
    verbose: bool = True,
    tuition_mode: str = "full",
    gauntlet: bool = False,
    live_path: str | None = None,
    repeats: int = 1,
) -> dict:
    cfg = load_config()
    tuition_text = load_tuition(tuition_mode)
    rng = random.Random(seed)
    elo = Elo()
    bb_deltas: dict[str, list[float]] = {c.label: [] for c in competitors}
    records: dict[str, list[int]] = {c.label: [0, 0, 0] for c in competitors}  # [W, L, tie]
    pairings: dict = {}  # head-to-head aggregate, keyed by sorted (a, b)

    players = {c.label: _build_player(cfg, c, tuition_text) for c in competitors}
    matches: list = []
    analyzer = _SoundnessAnalyzer()  # per-decision EV vs perfect (no-op if equity.py absent)

    live = None
    if live_path:
        from .live import LiveBroadcast
        live = LiveBroadcast(live_path)

    # Precompute which (i, j) pairs will actually run.
    planned = []
    for i in range(len(competitors)):
        for j in range(i + 1, len(competitors)):
            ca, cb = competitors[i], competitors[j]
            if gauntlet:
                both_llm = ca.model not in ANCHORS and cb.model not in ANCHORS
                if both_llm and ca.model != cb.model:
                    continue
            planned.append((i, j))
    total_matches = len(planned)

    if live:
        live.set_schedule([{"a": competitors[i].label, "b": competitors[j].label} for i, j in planned], stack, bb)
        for c in competitors:  # stream LLM tokens to the broadcast
            if isinstance(players[c.label], LLMPlayer):
                players[c.label].on_stream = live.stream_token

    if verbose:
        tn = f"{tuition_mode} ({len(tuition_text)} chars)" if tuition_text else "MISSING"
        print(f"Bake-off: {len(competitors)} competitors, {hands} hands/match x{repeats} round(s), "
              f"duplicate={'on' if duplicate else 'off'}, gauntlet={'on' if gauntlet else 'off'}, "
              f"tuition={tn}\n", flush=True)

    def snapshot(status: str) -> dict:
        sound = analyzer.summary(bb, bb_deltas)
        ratings = []
        for c in competitors:
            lo, hi = bootstrap_ci(bb_deltas[c.label])
            w, l, t = records[c.label]
            ratings.append({"label": c.label, "model": c.model, "tuition": c.tuition,
                            "elo": round(elo.get(c.label), 1),
                            "bb100": round(bb_per_100(bb_deltas[c.label]), 2),
                            "ci": [round(lo, 1), round(hi, 1)],
                            "hands": len(bb_deltas[c.label]),
                            "won_bb": round(sum(bb_deltas[c.label]), 1),
                            "wins": w, "losses": l, "ties": t,
                            "soundness": sound.get(c.label, {})})
        return {
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "config": {"hands": hands, "stack": stack, "sb": sb, "bb": bb, "seed": seed,
                       "duplicate": duplicate, "repeats": repeats,
                       "gauntlet": gauntlet, "tuition_mode": tuition_mode,
                       "tuition_corpus": bool(tuition_text),
                       "tuition_chars": len(tuition_text) if tuition_text else 0,
                       "status": status},
            "competitors": [{"label": c.label, "model": c.model, "tuition": c.tuition} for c in competitors],
            "ratings": ratings,
            "head_to_head": list(pairings.values()),
            "matches": matches[-150:],  # recent games (keep the file small over long runs)
            "usage": {c.label: _usage_of(players[c.label]) for c in competitors},
        }

    def checkpoint(status: str = "running") -> dict:
        results = snapshot(status)
        if out_path:
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(results, f, indent=2)
            with open(out_path.rsplit(".", 1)[0] + ".md", "w") as f:
                f.write(report.render(results))
        return results

    def event_sink(labels):
        analyzer.set_labels(labels)
        if live:
            def combined(ev):
                analyzer.on_event(ev)
                live.on_event(ev)
            return combined
        return analyzer.on_event

    def record_pairing(a, b, chips_a):
        key = tuple(sorted([a, b]))
        pr = pairings.setdefault(key, {"a": key[0], "b": key[1], "games": 0,
                                       "chips_a": 0, "a_wins": 0, "b_wins": 0, "ties": 0})
        pr["games"] += 1
        chips_first = chips_a if key[0] == a else -chips_a
        pr["chips_a"] += chips_first
        pr["a_wins"] += chips_first > 0
        pr["b_wins"] += chips_first < 0
        pr["ties"] += chips_first == 0

    # ---- round-robin, repeated to accumulate toward statistical significance ----
    for rnd in range(repeats):
        if live:
            live.state["round"] = rnd + 1
        for match_no, (i, j) in enumerate(planned, 1):
            ca, cb = competitors[i], competitors[j]
            pa, pb = players[ca.label], players[cb.label]
            if live:
                live.set_match(ca.label, cb.label, match_no, total_matches,
                               snapshot("running")["ratings"], stack)
            t0 = time.time()
            res = play_session(pa, pb, hands, stack, sb, bb, random.Random(rng.random()),
                               duplicate=duplicate, on_event=event_sink([ca.label, cb.label]))
            dt = time.time() - t0
            chips_a = res.chips[0]
            score_a = 1.0 if chips_a > 0 else (0.0 if chips_a < 0 else 0.5)
            elo.update_match(ca.label, cb.label, score_a)
            bb_deltas[ca.label].extend(res.bb_deltas)
            bb_deltas[cb.label].extend(-d for d in res.bb_deltas)
            if chips_a > 0:
                records[ca.label][0] += 1
                records[cb.label][1] += 1
            elif chips_a < 0:
                records[ca.label][1] += 1
                records[cb.label][0] += 1
            else:
                records[ca.label][2] += 1
                records[cb.label][2] += 1
            record_pairing(ca.label, cb.label, chips_a)
            matches.append({"a": ca.label, "b": cb.label, "hands": hands, "round": rnd + 1,
                            "chips_a": chips_a, "bb100_a": round(bb_per_100(res.bb_deltas), 2),
                            "seconds": round(dt, 1)})
            if verbose:
                print(f"  r{rnd + 1} [{match_no}/{total_matches}] {ca.label:>18} vs {cb.label:<18} "
                      f"A={chips_a:+7d}  ({dt:5.1f}s)", flush=True)
            if live:
                live.complete_match(match_no, chips_a, snapshot("running")["ratings"])
            checkpoint()

    if live:
        live.finish()
    results = checkpoint("complete")
    if verbose and out_path:
        print(f"\nSaved results -> {out_path}", flush=True)
    return results
