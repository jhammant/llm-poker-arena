"""Simple rule-based tight-aggressive baseline.

Not GTO and not trying to be — it just plays sanely (raises strong hands, folds
trash, respects pot odds) so it sits clearly above the random noise floor and
below any competent LLM. Useful as a fixed yardstick on the leaderboard.
"""
from __future__ import annotations

from .. import evaluator
from ..actions import CALL, CHECK, FOLD, RAISE, Action
from ..cards import rank_of, suit_of
from .base import Player


class HeuristicPlayer(Player):
    def __init__(self, name: str = "heuristic"):
        self.name = name

    def _preflop_strength(self, hole: list[int]) -> float:
        r_hi, r_lo = sorted((rank_of(hole[0]), rank_of(hole[1])), reverse=True)
        suited = suit_of(hole[0]) == suit_of(hole[1])
        pair = r_hi == r_lo
        hi = r_hi + 2  # 2..14
        if pair:
            return min(0.5 + hi / 14.0 * 0.5, 1.0)
        score = hi / 14.0 * 0.5 + (r_lo + 2) / 14.0 * 0.2
        if suited:
            score += 0.08
        gap = r_hi - r_lo
        if gap == 1:
            score += 0.05
        elif gap >= 4:
            score -= 0.08
        return min(max(score, 0.0), 1.0)

    def _postflop_strength(self, hole: list[int], board: list[int]) -> float:
        # treys score is 1 (best, royal flush) .. 7462 (worst, 7-high). Normalise
        # to [0, 1]; this distinguishes top pair from bottom pair, unlike the
        # coarse 9-way hand class.
        score = evaluator.evaluate(board, hole)
        return 1.0 - (score - 1) / 7461.0

    def _raise_to(self, obs, legal, frac: float) -> int:
        target = obs.street_committed[obs.hero] + legal.call_amount + int(obs.pot * frac)
        return max(legal.min_raise_to, min(target, legal.max_raise_to))

    def act(self, obs):
        legal = obs.legal
        if obs.street == "preflop":
            strength = self._preflop_strength(obs.hole)
        else:
            strength = self._postflop_strength(obs.hole, obs.board)

        call_cost = legal.call_amount
        pot_odds = call_cost / (obs.pot + call_cost) if call_cost > 0 else 0.0

        # Strong: raise for value.
        if strength > 0.75 and legal.can_raise:
            return Action(RAISE, self._raise_to(obs, legal, 0.75),
                          note=f"strong ({strength:.2f}), value raise")
        # Decent: bet/call.
        if strength > 0.55:
            if legal.can_check:
                if legal.can_raise and strength > 0.65:
                    return Action(RAISE, self._raise_to(obs, legal, 0.5), note="bet for value")
                return Action(CHECK)
            if legal.can_call and strength >= pot_odds + 0.1:
                return Action(CALL, note=f"call, ok odds ({strength:.2f} vs {pot_odds:.2f})")
            return Action(CHECK) if legal.can_check else Action(FOLD)
        # Weak.
        if legal.can_check:
            return Action(CHECK)
        if legal.can_call and strength >= pot_odds and call_cost <= obs.big_blind * 2:
            return Action(CALL, note="cheap speculative call")
        return Action(FOLD)
