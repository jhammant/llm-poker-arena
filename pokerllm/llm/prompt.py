"""Render an Observation into chat messages, and parse the model's reply.

The action protocol is plain JSON (not tool-calling) because support for
tools/structured-output varies wildly across local models; a single flat JSON
object parses reliably everywhere, and the engine sanitises anything malformed.
"""
from __future__ import annotations

import json
import re

from .. import cards
from ..actions import CALL, CHECK, FOLD, RAISE, Action

SYSTEM = """You are an expert heads-up No-Limit Texas Hold'em player. You play to \
maximise long-term profit in chips, using position, pot odds, hand strength and \
sensible aggression. You are given the current state and the exact legal actions.

Respond with ONLY a JSON object and nothing else:
{"action": "fold" | "check" | "call" | "raise", "amount": <int>, "reasoning": "<one short sentence>"}

- "amount" matters only for "raise": it is the TOTAL chips you commit on this \
street (i.e. raise TO that number), and must be within the allowed min/max shown.
- Use "check" only when there is nothing to call; otherwise choose call, raise, or fold.
- Output the JSON object only: no markdown, no code fences, no extra text."""


def _position_name(obs) -> str:
    if obs.hero == obs.button:
        return "button / small blind (acts first preflop, last postflop)"
    return "big blind (acts last preflop, first postflop)"


def render_state(obs) -> str:
    hero, opp = obs.hero, 1 - obs.hero
    lines = [
        f"Street: {obs.street}",
        f"Your position: {_position_name(obs)}",
        f"Your hole cards: {cards.cards_str(obs.hole)}",
        f"Board: {cards.cards_str(obs.board)}",
        f"Pot: {obs.pot}   (big blind = {obs.big_blind})",
        f"Your stack behind: {obs.stacks[hero]}   Opponent stack behind: {obs.stacks[opp]}",
        f"Committed this street — you: {obs.street_committed[hero]}, opponent: {obs.street_committed[opp]}",
        f"Amount to call: {obs.to_call}",
    ]
    if obs.history:
        hist = []
        for street, seat, act in obs.history:
            who = "you" if seat == hero else "opp"
            hist.append(f"{street}/{who}:{act}")
        lines.append("Action history: " + " | ".join(hist))

    legal = obs.legal
    opts = []
    if legal.can_fold:
        opts.append("fold")
    if legal.can_check:
        opts.append("check")
    if legal.can_call:
        opts.append(f"call (costs {legal.call_amount})")
    if legal.can_raise:
        opts.append(f"raise to an integer in [{legal.min_raise_to}, {legal.max_raise_to}]")
    lines.append("Legal actions: " + "; ".join(opts))
    return "\n".join(lines)


def build_messages(obs, system_extra: str | None = None) -> list[dict]:
    system = SYSTEM
    if system_extra:
        system = SYSTEM + "\n\nSTRATEGY NOTES (apply these):\n" + system_extra
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": render_state(obs) + "\n\nYour action (JSON only):"},
    ]


_ACTION_MAP = {"fold": FOLD, "check": CHECK, "call": CALL, "raise": RAISE, "bet": RAISE}


def parse_action(text: str) -> Action | None:
    """Extract a flat JSON action object from the model's reply. None on failure."""
    if not text:
        return None
    # Strip reasoning wrappers some models inline into the content channel.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = re.findall(r"\{[^{}]*\}", text, re.DOTALL) or re.findall(r"\{.*\}", text, re.DOTALL)
    for blob in candidates:
        try:
            data = json.loads(blob)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        kind = _ACTION_MAP.get(str(data.get("action", "")).lower().strip())
        if kind is None:
            continue
        raw_amt = data.get("amount", data.get("raise_to", 0))
        try:
            amount = int(float(raw_amt))
        except Exception:
            amount = 0
        reasoning = str(data.get("reasoning", ""))[:200]
        return Action(kind, amount, note=reasoning)
    return None
