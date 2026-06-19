# pokerllm — an LLM poker arena

Pit different LLMs against each other at **heads-up No-Limit Texas Hold'em**, rate
them with **Elo + BB/100** (with confidence intervals and duplicate-poker variance
reduction), and run the experiment: *does a weaker model given poker strategy docs
beat a stronger model — or the same model without them?*

Models run locally for free (**LM Studio** / **Ollama** on Apple Silicon) or via
**OpenRouter** (cloud). They all speak the OpenAI-compatible API, so one client
handles every provider.

## Status

| Phase | What | State |
|---|---|---|
| 1 | Engine (heads-up NLHE) + Elo/BB-100 ratings + duplicate poker | ✅ done, verified by self-play |
| 2 | LLM players (LM Studio / Ollama / OpenRouter) + prompt/action layer | ⏳ next |
| 2 | Live web dashboard (watch hands + leaderboard) | ⏳ next |
| 2 | Strategy-docs corpus + RAG retrieval | ⏳ next |
| 3 | The experiment harness (weak+docs vs strong, etc.) | ⏳ planned |

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# verify the engine + rating pipeline with free self-play (no models, no cost)
python -m pokerllm.run demo
python -m pokerllm.run league --hands 2000
pytest -q
```

A correct build shows the `heuristic` player clearly on top with positive BB/100,
random players negative, and the chip totals zero-summing.

## Design

- **`pokerllm/engine.py`** — pure heads-up NLHE state machine. Button posts the
  small blind; defensive — any illegal action a player returns is sanitised to the
  closest legal one (check → call → fold), so a misbehaving LLM can't crash a run.
- **`pokerllm/evaluator.py` / `cards.py`** — hand strength via the battle-tested
  `treys` evaluator; a seeded deck so shuffles are reproducible and can be replayed
  with swapped seats (duplicate poker).
- **`pokerllm/players/`** — `Player` interface; `RandomPlayer` (noise floor) and
  `HeuristicPlayer` (a sane tight-aggressive yardstick). `LLMPlayer` lands in phase 2.
- **`pokerllm/match.py`** — sessions of N hands, alternating button, optional
  duplicate (mirrored-card) play to cancel the luck of the deal.
- **`pokerllm/rating.py`** — Elo ladder + BB/100 with bootstrap confidence intervals.
- **`config/models.yaml`** — the model roster (local-first; OpenRouter wired but
  disabled until local play is working).

## Why Elo *and* BB/100

Poker is high-variance, so any single rating is misleading on a small sample.
BB/100 (big blinds won per 100 hands) is the standard skill metric and its
bootstrap CI tells you whether a gap is real; Elo gives an intuitive head-to-head
ladder. Duplicate poker (same cards, swapped seats) cancels dealing luck so far
fewer hands are needed for trustworthy numbers.
