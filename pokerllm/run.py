"""CLI entry point.

Phase 1: round-robin among built-in (free) players to verify the engine +
rating pipeline end-to-end. LLM players, the web dashboard, and the strategy-docs
experiment are layered on next.

    python -m pokerllm.run demo                 # quick random vs heuristic
    python -m pokerllm.run league --hands 2000  # full round-robin
"""
from __future__ import annotations

import argparse
import random

from .match import play_session
from .players.heuristic import HeuristicPlayer
from .players.random_player import RandomPlayer
from .rating import Elo, bb_per_100, bootstrap_ci


def build_roster() -> list:
    return [
        HeuristicPlayer("heuristic"),
        RandomPlayer("random_tight", seed=1, aggression=0.2),
        RandomPlayer("random_loose", seed=2, aggression=0.6),
    ]


def run_league(hands: int, stack: int, sb: int, bb: int, seed: int, duplicate: bool) -> None:
    rng = random.Random(seed)
    roster = build_roster()
    elo = Elo()
    bb_deltas: dict[str, list[float]] = {p.name: [] for p in roster}

    print(f"Round-robin: {len(roster)} players, {hands} hands/match, "
          f"duplicate={'on' if duplicate else 'off'}\n")
    for i in range(len(roster)):
        for j in range(i + 1, len(roster)):
            p_a, p_b = roster[i], roster[j]
            res = play_session(p_a, p_b, hands, stack, sb, bb,
                               random.Random(rng.random()), duplicate=duplicate)
            chips_a = res.chips[0]
            score_a = 1.0 if chips_a > 0 else (0.0 if chips_a < 0 else 0.5)
            elo.update_match(p_a.name, p_b.name, score_a)
            bb_deltas[p_a.name].extend(res.bb_deltas)
            bb_deltas[p_b.name].extend(-d for d in res.bb_deltas)
            winner = "A" if score_a == 1 else "B" if score_a == 0 else "tie"
            print(f"  {p_a.name:>13} vs {p_b.name:<13}  A_chips={chips_a:+7d}  ({winner})")

    _leaderboard(roster, elo, bb_deltas)


def _make_printer():
    """Pretty-print engine events for a single watched session."""
    def printer(e: dict) -> None:
        t = e["type"]
        if t == "hand_start":
            print(f"\n--- new hand (button=seat{e['button']}) holes={e['holes']} ---")
        elif t == "board":
            print(f"  [{e['street']}] board: {e['board']}")
        elif t == "action":
            amt = f" to {e['amount']}" if e["action"] == "raise" else ""
            note = f"   // {e['note']}" if e.get("note") else ""
            print(f"    seat{e['seat']}: {e['action']}{amt}  (pot {e['pot']}){note}")
        elif t == "result":
            print(f"  => {e['note']}  board={e['board']} holes={e['holes']} deltas={e['deltas']}")
        elif t == "error":
            print(f"    !! seat{e['seat']} error: {e['error']}")
    return printer


def run_smoke(model: str, hands: int, stack: int, sb: int, bb: int, seed: int) -> None:
    """Watch one local/cloud LLM play vs the heuristic — proves the LLM loop works."""
    from .config import load_config, make_player

    cfg = load_config()
    llm = make_player(cfg, model)
    opp = HeuristicPlayer("heuristic")
    print(f"Smoke test: {model} (LLM) vs heuristic — {hands} hands\n")
    res = play_session(llm, opp, hands, stack, sb, bb, random.Random(seed),
                       duplicate=False, on_event=_make_printer())
    u = llm.usage
    print(f"\nResult: {model} chips {res.chips[0]:+d}  ({res.chips[0] / bb:+.1f} bb)")
    print(f"LLM calls: {u.calls}  avg latency: {u.avg_latency_s:.2f}s  "
          f"tokens(p/c): {u.prompt_tokens}/{u.completion_tokens}  "
          f"parse_failures: {u.parse_failures}  errors: {u.errors}")


def run_bakeoff_cli(models, tuition_models, hands, ref_hands, stack, sb, bb, seed,
                    duplicate, out, tuition_mode="full", gauntlet=False, live=None):
    import datetime

    from . import report
    from .arena import Competitor, run_bakeoff

    comps: list = []
    seen: set = set()
    for m in models:
        if m and m not in seen:
            comps.append(Competitor(label=m, model=m))
            seen.add(m)
    for m in tuition_models:
        if m and m not in seen:  # ensure a plain variant exists to compare against
            comps.append(Competitor(label=m, model=m))
            seen.add(m)
        if m:
            tag = "+docs" if tuition_mode == "lite" else "+tuition"
            comps.append(Competitor(label=f"{m}{tag}", model=m, tuition=True))

    # Preflight: fail fast on an unknown model name instead of mid-run.
    from .arena import ANCHORS
    from .config import load_config
    known = {p["name"] for p in load_config().get("players", [])} | ANCHORS
    missing = sorted({c.model for c in comps if c.model not in known})
    if missing:
        print(f"ERROR: unknown model name(s) not in config/models.yaml: {', '.join(missing)}")
        print(f"Known: {', '.join(sorted(known))}")
        return

    if not out:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        out = f"runs/bakeoff_{ts}.json"
    res = run_bakeoff(comps, hands, stack, sb, bb, seed, duplicate, ref_hands,
                      out_path=out, tuition_mode=tuition_mode, gauntlet=gauntlet, live_path=live)
    md_path = out.rsplit(".", 1)[0] + ".md"
    with open(md_path, "w") as f:
        f.write(report.render(res))
    print(f"Report -> {md_path}")


def _leaderboard(roster, elo: Elo, bb_deltas: dict[str, list[float]]) -> None:
    print("\n=== Leaderboard ===")
    rows = []
    for p in roster:
        d = bb_deltas[p.name]
        lo, hi = bootstrap_ci(d)
        rows.append((elo.get(p.name), p.name, bb_per_100(d), lo, hi, len(d)))
    rows.sort(reverse=True)
    print(f"{'Elo':>6}  {'player':<14} {'BB/100':>8}  {'95% CI (BB/100)':>20}  {'hands':>6}")
    print("-" * 64)
    for elo_v, name, b100, lo, hi, n in rows:
        print(f"{elo_v:6.0f}  {name:<14} {b100:8.2f}  [{lo:7.1f}, {hi:7.1f}]  {n:6d}")


def main() -> None:
    ap = argparse.ArgumentParser(description="LLM poker arena (phase 1: self-play verification)")
    sub = ap.add_subparsers(dest="cmd")
    for cmd in ("demo", "league"):
        p = sub.add_parser(cmd)
        p.add_argument("--hands", type=int, default=None)
        p.add_argument("--stack", type=int, default=200, help="starting stack (100bb at bb=2)")
        p.add_argument("--sb", type=int, default=1)
        p.add_argument("--bb", type=int, default=2)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--no-duplicate", action="store_true")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--model", required=True, help="player name from config/models.yaml")
    smoke.add_argument("--hands", type=int, default=5)
    smoke.add_argument("--stack", type=int, default=200)
    smoke.add_argument("--sb", type=int, default=1)
    smoke.add_argument("--bb", type=int, default=2)
    smoke.add_argument("--seed", type=int, default=42)

    bo = sub.add_parser("bakeoff")
    bo.add_argument("--models", default="heuristic,random",
                    help="comma-separated competitor names (config models, or heuristic/random)")
    bo.add_argument("--tuition", default="",
                    help="comma-separated models to ALSO run with the strategy corpus (adds +tuition variant)")
    bo.add_argument("--hands", type=int, default=200)
    bo.add_argument("--reference-hands", type=int, default=0, help="extra hands vs heuristic baseline")
    bo.add_argument("--stack", type=int, default=200)
    bo.add_argument("--sb", type=int, default=1)
    bo.add_argument("--bb", type=int, default=2)
    bo.add_argument("--seed", type=int, default=42)
    bo.add_argument("--duplicate", action="store_true", help="mirrored-card play (2x games, tighter CIs)")
    bo.add_argument("--tuition-mode", choices=["full", "lite"], default="full",
                    help="full = whole corpus; lite = condensed cheat-sheet")
    bo.add_argument("--gauntlet", action="store_true",
                    help="skip cross-model LLM-vs-LLM; keep anchor matches + same-model tuition A/B")
    bo.add_argument("--live", default=None, help="path to write the live broadcast state JSON")
    bo.add_argument("--out", default=None)

    rep = sub.add_parser("report")
    rep.add_argument("json", help="path to a saved bakeoff JSON")
    rep.add_argument("--out", default=None)

    dash = sub.add_parser("dashboard")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=8000)

    args = ap.parse_args()

    if args.cmd == "demo":
        run_league(args.hands or 300, args.stack, args.sb, args.bb, args.seed, not args.no_duplicate)
    elif args.cmd == "league":
        run_league(args.hands or 2000, args.stack, args.sb, args.bb, args.seed, not args.no_duplicate)
    elif args.cmd == "smoke":
        run_smoke(args.model, args.hands, args.stack, args.sb, args.bb, args.seed)
    elif args.cmd == "bakeoff":
        models = [m.strip() for m in args.models.split(",") if m.strip()]
        tuition = [m.strip() for m in args.tuition.split(",") if m.strip()]
        run_bakeoff_cli(models, tuition, args.hands, args.reference_hands,
                        args.stack, args.sb, args.bb, args.seed, args.duplicate, args.out,
                        tuition_mode=args.tuition_mode, gauntlet=args.gauntlet, live=args.live)
    elif args.cmd == "report":
        from . import report
        out = args.out or args.json.rsplit(".", 1)[0] + ".md"
        report.render_file(args.json, out)
        print(f"Report -> {out}")
    elif args.cmd == "dashboard":
        import uvicorn
        print(f"Dashboard: http://{args.host}:{args.port}")
        uvicorn.run("pokerllm.web.server:app", host=args.host, port=args.port, log_level="warning")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
