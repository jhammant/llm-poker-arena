"""Random legal-action player — the noise floor for calibrating ratings."""
from __future__ import annotations

import random

from ..actions import CALL, CHECK, FOLD, RAISE, Action
from .base import Player


class RandomPlayer(Player):
    def __init__(self, name: str = "random", seed: int | None = None, aggression: float = 0.3):
        self.name = name
        self.rng = random.Random(seed)
        self.aggression = aggression

    def act(self, obs):
        legal = obs.legal
        if legal.can_raise and self.rng.random() < self.aggression:
            lo, hi = legal.min_raise_to, legal.max_raise_to
            # bias toward smaller raises
            top = min(hi, lo + max(1, (hi - lo) // 3))
            return Action(RAISE, self.rng.randint(lo, top))
        if legal.can_check:
            return Action(CHECK)
        if legal.can_call and self.rng.random() < 0.7:
            return Action(CALL)
        return Action(FOLD)
