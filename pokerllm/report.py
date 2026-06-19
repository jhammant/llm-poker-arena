"""Render a Markdown report from an arena results dict (or saved JSON)."""
from __future__ import annotations

import json


def _find_match(matches: list[dict], x: str, y: str):
    """Return (chips_for_x, bb100_for_x) for the x-vs-y match, or (None, None)."""
    for m in matches:
        if m["a"] == x and m["b"] == y:
            return m["chips_a"], m["bb100_a"]
        if m["a"] == y and m["b"] == x:
            return -m["chips_a"], -m["bb100_a"]
    return None, None


def render(results: dict) -> str:
    cfg = results["config"]
    ratings = results["ratings"]
    matches = results.get("matches", [])
    usage = results.get("usage", {})
    reference = results.get("reference", {})

    out: list[str] = []
    w = out.append

    status = cfg.get("status", "complete")
    w("# LLM Poker Bake-off Report")
    w("")
    badge = {"running": "🟡 RUNNING (live, updates each match)", "complete": "🟢 complete"}.get(status, status)
    w(f"_Generated {results['created']}_ &nbsp;·&nbsp; **{badge}** &nbsp;·&nbsp; {len(matches)} matches done")
    w("")
    w(f"**Game:** heads-up No-Limit Hold'em &nbsp;·&nbsp; "
      f"{cfg['hands']} hands/match &nbsp;·&nbsp; stack {cfg['stack']} (bb={cfg['bb']}) &nbsp;·&nbsp; "
      f"duplicate poker **{'on' if cfg['duplicate'] else 'off'}** &nbsp;·&nbsp; "
      f"tuition corpus **{'injected' if cfg['tuition_corpus'] else 'absent'}**"
      + (f" ({cfg.get('tuition_chars', 0)} chars)" if cfg['tuition_corpus'] else "") + ".")
    w("")
    w("Ratings: **Elo** from head-to-head session win/loss; **BB/100** = big blinds "
      "won per 100 hands (the standard skill metric) with a bootstrap 95% CI. "
      "A CI that excludes 0 means the edge is real signal, not variance.")
    w("")

    # ---- Leaderboard ----
    w("## Leaderboard")
    w("")
    w("| # | Competitor | Elo | BB/100 | 95% CI | Hands | Tuition |")
    w("|---:|---|---:|---:|:---:|---:|:---:|")
    for rank, r in enumerate(sorted(ratings, key=lambda x: x["elo"], reverse=True), 1):
        ci = f"[{r['ci'][0]:+.0f}, {r['ci'][1]:+.0f}]"
        tui = "✅" if r["tuition"] else ""
        w(f"| {rank} | {r['label']} | {r['elo']:.0f} | {r['bb100']:+.1f} | {ci} | {r['hands']} | {tui} |")
    w("")

    # ---- Tuition effect ----
    by_model: dict[str, dict] = {}
    for r in ratings:
        slot = by_model.setdefault(r["model"], {})
        slot["tuition" if r["tuition"] else "plain"] = r
    paired = {m: v for m, v in by_model.items() if "plain" in v and "tuition" in v}
    if paired:
        w("## Does tuition help? (same model, with vs without strategy docs)")
        w("")
        w("| Model | BB/100 plain | BB/100 +tuition | Δ BB/100 | Head-to-head (tuition's chips) | Verdict |")
        w("|---|---:|---:|---:|---:|:---|")
        for model, v in paired.items():
            p, t = v["plain"], v["tuition"]
            delta = t["bb100"] - p["bb100"]
            chips, _ = _find_match(matches, t["label"], p["label"])
            h2h = f"{chips:+d}" if chips is not None else "—"
            if chips is not None and chips > 0 and delta > 0:
                verdict = "tuition helped"
            elif chips is not None and chips < 0 and delta < 0:
                verdict = "tuition hurt"
            else:
                verdict = "inconclusive"
            w(f"| {model} | {p['bb100']:+.1f} | {t['bb100']:+.1f} | {delta:+.1f} | {h2h} | {verdict} |")
        w("")
        w("> Head-to-head is the cleanest signal: the same model plays itself, one "
          "copy reading the strategy docs. Positive chips = the tutored copy won.")
        w("")

    # ---- Reference gauntlet ----
    if reference:
        w("## Gauntlet vs the heuristic baseline")
        w("")
        w("A fixed, free yardstick: every competitor also plays the rule-based "
          "heuristic, giving a comparable BB/100 across models.")
        w("")
        w("| Competitor | BB/100 vs heuristic | 95% CI | Hands |")
        w("|---|---:|:---:|---:|")
        for label, ref in sorted(reference.items(), key=lambda kv: kv[1]["bb100"], reverse=True):
            ci = f"[{ref['ci'][0]:+.0f}, {ref['ci'][1]:+.0f}]"
            w(f"| {label} | {ref['bb100']:+.1f} | {ci} | {ref['hands']} |")
        w("")

    # ---- Head-to-head results ----
    if matches:
        w("## Match results")
        w("")
        w("| A | B | A's chips | A's BB/100 | Time |")
        w("|---|---|---:|---:|---:|")
        for m in matches:
            w(f"| {m['a']} | {m['b']} | {m['chips_a']:+d} | {m['bb100_a']:+.1f} | {m['seconds']:.0f}s |")
        w("")

    # ---- Speed & cost ----
    llm_usage = {k: u for k, u in usage.items() if u.get("llm")}
    if llm_usage:
        w("## Speed, tokens & reliability")
        w("")
        w("| Competitor | Decisions | Avg latency | Tokens (prompt/completion) | Parse fails | Errors |")
        w("|---|---:|---:|---:|---:|---:|")
        for label, u in llm_usage.items():
            w(f"| {label} | {u['calls']} | {u['avg_latency_s']:.2f}s | "
              f"{u['prompt_tokens']}/{u['completion_tokens']} | {u['parse_failures']} | {u['errors']} |")
        w("")

    # ---- Caveats ----
    w("## Caveats")
    w("")
    w("- Poker is high-variance; trust BB/100 only when its CI excludes 0. Small "
      "samples can rank noise above skill.")
    if not cfg["duplicate"]:
        w("- Duplicate poker is **off** here, so card luck is not cancelled — wider CIs. "
          "Re-run with `--duplicate` (2× the games) to tighten.")
    w("- Tuition here is the full corpus stuffed into the system prompt; "
      "retrieval (RAG) would inject only the relevant snippet per decision.")
    return "\n".join(out)


def render_file(json_path: str, md_path: str) -> None:
    with open(json_path) as f:
        results = json.load(f)
    with open(md_path, "w") as f:
        f.write(render(results))
