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
from .players.random_player import RandomPlayer
from .rating import Elo, bb_per_100, bootstrap_ci

STRATEGY_DIR = "strategy_docs"
CHEATSHEET = "tuition/cheatsheet.md"
TUITION_CHAR_CAP = 16000
ANCHORS = {"heuristic", "random"}


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
    else:
        extra = tuition_text if comp.tuition else None
        p = make_player(cfg, comp.model, system_extra=extra)
        p.name = comp.label
    return p


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
) -> dict:
    cfg = load_config()
    tuition_text = load_tuition(tuition_mode)
    rng = random.Random(seed)
    elo = Elo()
    bb_deltas: dict[str, list[float]] = {c.label: [] for c in competitors}

    players = {c.label: _build_player(cfg, c, tuition_text) for c in competitors}
    matches: list = []
    reference: dict = {}

    live = None
    if live_path:
        from .live import LiveBroadcast
        live = LiveBroadcast(live_path)

    # Precompute which (i, j) pairs will actually run, so the broadcast can show
    # "match X of N".
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

    if verbose:
        tn = f"{tuition_mode} ({len(tuition_text)} chars)" if tuition_text else "MISSING"
        print(f"Bake-off: {len(competitors)} competitors, {hands} hands/match, "
              f"duplicate={'on' if duplicate else 'off'}, gauntlet={'on' if gauntlet else 'off'}, "
              f"tuition={tn}\n", flush=True)

    def snapshot(status: str) -> dict:
        ratings = []
        for c in competitors:
            lo, hi = bootstrap_ci(bb_deltas[c.label])
            ratings.append({"label": c.label, "model": c.model, "tuition": c.tuition,
                            "elo": round(elo.get(c.label), 1),
                            "bb100": round(bb_per_100(bb_deltas[c.label]), 2),
                            "ci": [round(lo, 1), round(hi, 1)],
                            "hands": len(bb_deltas[c.label])})
        return {
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "config": {"hands": hands, "stack": stack, "sb": sb, "bb": bb, "seed": seed,
                       "duplicate": duplicate, "reference_hands": reference_hands,
                       "gauntlet": gauntlet, "tuition_mode": tuition_mode,
                       "tuition_corpus": bool(tuition_text),
                       "tuition_chars": len(tuition_text) if tuition_text else 0,
                       "status": status},
            "competitors": [{"label": c.label, "model": c.model, "tuition": c.tuition} for c in competitors],
            "ratings": ratings,
            "reference": reference,
            "matches": matches,
            "usage": {c.label: _usage_of(players[c.label]) for c in competitors},
        }

    def checkpoint(status: str = "running") -> dict:
        """Write JSON + Markdown after each match so progress is live & crash-safe."""
        results = snapshot(status)
        if out_path:
            os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
            with open(out_path, "w") as f:
                json.dump(results, f, indent=2)
            with open(out_path.rsplit(".", 1)[0] + ".md", "w") as f:
                f.write(report.render(results))
        return results

    # ---- round-robin (Elo + head-to-head BB/100), checkpointing + streaming ----
    for match_no, (i, j) in enumerate(planned, 1):
        ca, cb = competitors[i], competitors[j]
        pa, pb = players[ca.label], players[cb.label]
        if live:
            live.set_match(ca.label, cb.label, match_no, total_matches,
                           snapshot("running")["ratings"], stack)
        t0 = time.time()
        res = play_session(pa, pb, hands, stack, sb, bb, random.Random(rng.random()),
                           duplicate=duplicate, on_event=(live.on_event if live else None))
        dt = time.time() - t0
        chips_a = res.chips[0]
        score_a = 1.0 if chips_a > 0 else (0.0 if chips_a < 0 else 0.5)
        elo.update_match(ca.label, cb.label, score_a)
        bb_deltas[ca.label].extend(res.bb_deltas)
        bb_deltas[cb.label].extend(-d for d in res.bb_deltas)
        matches.append({"a": ca.label, "b": cb.label, "hands": hands,
                        "chips_a": chips_a, "bb100_a": round(bb_per_100(res.bb_deltas), 2),
                        "seconds": round(dt, 1)})
        if verbose:
            print(f"  [{match_no}/{total_matches}] {ca.label:>20} vs {cb.label:<20} "
                  f"A={chips_a:+7d}  ({dt:5.1f}s)", flush=True)
        checkpoint()

    # ---- optional gauntlet vs the free heuristic (comparable yardstick) ----
    if reference_hands > 0:
        for c in competitors:
            ref = HeuristicPlayer("heuristic_ref")
            res = play_session(players[c.label], ref, reference_hands, stack, sb, bb,
                               random.Random(rng.random()), duplicate=duplicate)
            lo, hi = bootstrap_ci(res.bb_deltas)
            reference[c.label] = {"bb100": round(bb_per_100(res.bb_deltas), 2),
                                  "ci": [round(lo, 1), round(hi, 1)],
                                  "chips": res.chips[0], "hands": reference_hands}
            if verbose:
                print(f"  [ref] {c.label:>22} vs heuristic  bb/100={reference[c.label]['bb100']:+.1f}", flush=True)
            checkpoint()

    if live:
        live.finish()
    results = checkpoint("complete")
    if verbose and out_path:
        print(f"\nSaved results -> {out_path}", flush=True)
    return results
