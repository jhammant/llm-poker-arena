"""Elo ratings + BB/100 winrate with bootstrap confidence intervals.

Why both? Poker is high-variance, so a single rating number is misleading:
  * BB/100 is the standard skill metric (big blinds won per 100 hands), and the
    bootstrap CI tells you whether a gap is real signal or just noise.
  * Elo gives an intuitive head-to-head ladder from match win/loss results.
"""
from __future__ import annotations

import random


class Elo:
    def __init__(self, k: float = 24.0, base: float = 1500.0):
        self.k = k
        self.base = base
        self.ratings: dict[str, float] = {}

    def get(self, name: str) -> float:
        return self.ratings.setdefault(name, self.base)

    def update_match(self, a: str, b: str, score_a: float) -> None:
        """score_a: 1.0 = A won the session, 0.0 = B won, 0.5 = tie."""
        ra, rb = self.get(a), self.get(b)
        ea = 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))
        self.ratings[a] = ra + self.k * (score_a - ea)
        self.ratings[b] = rb + self.k * ((1.0 - score_a) - (1.0 - ea))


def bb_per_100(bb_deltas: list[float]) -> float:
    if not bb_deltas:
        return 0.0
    return 100.0 * sum(bb_deltas) / len(bb_deltas)


def bootstrap_ci(
    bb_deltas: list[float],
    iters: int = 2000,
    alpha: float = 0.05,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """95% CI on BB/100 by resampling hands with replacement."""
    n = len(bb_deltas)
    if n < 2:
        return (0.0, 0.0)
    rng = rng or random.Random(12345)
    means = []
    for _ in range(iters):
        total = 0.0
        for _ in range(n):
            total += bb_deltas[rng.randrange(n)]
        means.append(100.0 * total / n)
    means.sort()
    lo = means[int(alpha / 2 * iters)]
    hi = means[int((1 - alpha / 2) * iters)]
    return (lo, hi)
