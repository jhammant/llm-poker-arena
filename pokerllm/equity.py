"""Monte-Carlo poker equity + "perfect play" analyzer for heads-up NL Hold'em.

Pure stdlib + treys. Cards are treys integers. Hand strength comes from the
project evaluator (``evaluator.evaluate(board, hole)`` -> lower rank is stronger,
1 == best possible hand).

Public API:
  * ``hand_equity(hole, board, iters, rng)`` -> float
  * ``analyze_decision(...)`` -> dict (conservative blunder detector)
  * ``PerfectishPlayer`` -> equity-based baseline Player
"""
from __future__ import annotations

import random

from treys import Card

from . import evaluator
from .actions import CALL, CHECK, FOLD, RAISE, Action
from .players.base import Player

# All 52 cards as treys ints (built locally so this module stays self-contained).
_FULL_DECK: list[int] = [
    Card.new(r + s) for r in "23456789TJQKA" for s in "shdc"
]


def _remaining_deck(known: list[int]) -> list[int]:
    """Full 52-card deck minus the known (dealt) cards."""
    seen = set(known)
    return [c for c in _FULL_DECK if c not in seen]


def hand_equity(
    hole: list[int],
    board: list[int],
    iters: int = 300,
    rng: random.Random | None = None,
) -> float:
    """P(win) + 0.5 * P(tie) of ``hole`` vs ONE uniformly-random opponent hand.

    Monte-Carlo over the remaining deck: each iteration deals the opponent 2
    cards and completes the board to 5 from the remaining deck, then compares
    via ``evaluator.evaluate`` (lower rank == stronger).
    """
    rng = rng or random.Random()
    deck = _remaining_deck(list(hole) + list(board))
    need_board = 5 - len(board)
    sample_n = need_board + 2  # board completion + opponent's 2 hole cards

    if len(deck) < sample_n:
        # Not enough cards to run the sim (shouldn't happen in normal play).
        return 0.5

    wins = 0.0
    for _ in range(iters):
        draw = rng.sample(deck, sample_n)
        opp = draw[:2]
        full_board = board + draw[2:]
        hero_score = evaluator.evaluate(full_board, hole)
        opp_score = evaluator.evaluate(full_board, opp)
        if hero_score < opp_score:  # lower is stronger
            wins += 1.0
        elif hero_score == opp_score:
            wins += 0.5
    return wins / iters


def analyze_decision(
    hole: list[int],
    board: list[int],
    to_call: int,
    pot: int,
    action_kind: str,
    raise_to: int,
    can_check: bool,
    iters: int = 200,
    rng: random.Random | None = None,
) -> dict:
    """Conservatively judge whether a decision was a CLEAR EV mistake.

    Only obvious mistakes are flagged (wide 0.15 margins) to keep false
    positives low. Returns ``{"equity", "blunder", "ev_lost", "reason"}``.
    """
    eq = hand_equity(hole, board, iters, rng)
    pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0

    blunder = False
    ev_lost = 0.0
    reason = "no clear mistake"

    if action_kind == FOLD and to_call > 0 and eq >= pot_odds + 0.15:
        # Folded a clearly +EV call: gave up eq*(pot+to_call) - to_call chips.
        blunder = True
        ev_lost = max(0.0, eq * (pot + to_call) - to_call)
        reason = (
            f"folded a +EV call (eq {eq:.2f} vs pot odds {pot_odds:.2f})"
        )
    elif action_kind == CALL and eq <= pot_odds - 0.15:
        # Called clearly -EV: lost to_call - eq*(pot+to_call) chips.
        blunder = True
        ev_lost = max(0.0, to_call - eq * (pot + to_call))
        reason = (
            f"called a clearly -EV spot (eq {eq:.2f} vs pot odds {pot_odds:.2f})"
        )
    elif action_kind == FOLD and to_call == 0:
        # Folded when a free check was available — strictly dominated.
        blunder = True
        ev_lost = max(0.0, eq * pot)
        reason = "folded when a free check was available"

    return {
        "equity": round(eq, 3),
        "blunder": bool(blunder),
        "ev_lost": float(max(0.0, ev_lost)),
        "reason": reason,
    }


class PerfectishPlayer(Player):
    """Near-optimal equity-based baseline.

    Uses Monte-Carlo equity vs a random hand plus pot-odds discipline:
      * Strong (eq > 0.70): value-raise ~2/3 pot.
      * Medium (eq > 0.55): half-pot bet when checked to, else call if priced in.
      * Weak: check for free, otherwise call only with correct pot odds, else fold.
    Always returns a LEGAL action.
    """

    def __init__(self, name: str = "perfect-ish"):
        self.name = name

    def _raise_to(self, obs, legal, frac: float) -> int:
        """Raise TO total this street: current commit + call + frac of pot."""
        target = (
            obs.street_committed[obs.hero]
            + legal.call_amount
            + round(obs.pot * frac)
        )
        return max(legal.min_raise_to, min(target, legal.max_raise_to))

    def act(self, obs) -> Action:
        legal = obs.legal
        eq = hand_equity(obs.hole, obs.board, iters=250)
        call = legal.call_amount
        pot_odds = call / (obs.pot + call) if call > 0 else 0.0

        # Strong: value-raise ~2/3 pot.
        if eq > 0.70 and legal.can_raise:
            return Action(
                RAISE,
                self._raise_to(obs, legal, 0.66),
                note=f"value raise (eq {eq:.2f})",
            )

        # Medium: bet for thin value if checked to, else call when priced in.
        if eq > 0.55:
            if legal.can_check:
                if legal.can_raise:
                    return Action(
                        RAISE,
                        self._raise_to(obs, legal, 0.5),
                        note=f"thin value bet (eq {eq:.2f})",
                    )
                return Action(CHECK, note=f"check medium (eq {eq:.2f})")
            if legal.can_call and eq >= pot_odds:
                return Action(
                    CALL,
                    note=f"call, priced in (eq {eq:.2f} vs {pot_odds:.2f})",
                )
            return Action(CHECK) if legal.can_check else Action(
                FOLD, note=f"fold medium, bad odds (eq {eq:.2f})"
            )

        # Weak: prefer a free check, else only a correct pot-odds call.
        if legal.can_check:
            return Action(CHECK, note=f"check weak (eq {eq:.2f})")
        if legal.can_call and eq >= pot_odds:
            return Action(
                CALL,
                note=f"odds call (eq {eq:.2f} vs {pot_odds:.2f})",
            )
        return Action(FOLD, note=f"fold weak (eq {eq:.2f})")


if __name__ == "__main__":
    rng = random.Random(0)
    aa = hand_equity([Card.new("Ah"), Card.new("As")], [], iters=2000, rng=rng)
    o72 = hand_equity([Card.new("7h"), Card.new("2c")], [], iters=2000, rng=rng)
    print(f"AA preflop equity:  {aa:.3f}  (expect ~0.85)")
    print(f"72o preflop equity: {o72:.3f}  (expect ~0.35)")
