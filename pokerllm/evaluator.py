"""Hand strength via treys. Lower score = stronger hand.

treys returns a rank in [1, 7462] (1 == royal flush) and exposes 9 hand classes
(1 == straight flush ... 9 == high card).
"""
from __future__ import annotations

from treys import Evaluator

_EV = Evaluator()


def evaluate(board: list[int], hole: list[int]) -> int:
    """Best 5-card score from hole + board. Total cards must be in 5..7."""
    return _EV.evaluate(board, hole)


def hand_class(board: list[int], hole: list[int]) -> int:
    """1 (best, straight flush) .. 9 (worst, high card)."""
    return _EV.get_rank_class(evaluate(board, hole))


def class_name(score: int) -> str:
    return _EV.class_to_string(_EV.get_rank_class(score))
