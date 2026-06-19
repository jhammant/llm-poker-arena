"""Card + deck primitives built on treys integer cards.

A "card" is a treys integer (see ``treys.Card``). We keep our own seeded Deck so
shuffles are reproducible and so we can replay an identical deck with swapped
seats for duplicate (mirrored) poker — the standard variance-reduction trick
from poker-AI research (Cepheus/Pluribus).
"""
from __future__ import annotations

import random

from treys import Card

RANKS = "23456789TJQKA"
SUITS = "shdc"

# All 52 cards as treys ints.
FULL_DECK: list[int] = [Card.new(r + s) for r in RANKS for s in SUITS]


def shuffled_deck(rng: random.Random) -> list[int]:
    """Return a freshly shuffled 52-card deck (list of treys ints)."""
    deck = list(FULL_DECK)
    rng.shuffle(deck)
    return deck


def card_str(card: int) -> str:
    return Card.int_to_str(card)


def cards_str(cards: list[int]) -> str:
    return " ".join(Card.int_to_str(c) for c in cards) if cards else "-"


def rank_of(card: int) -> int:
    """0..12 for 2..A."""
    return Card.get_rank_int(card)


def suit_of(card: int) -> int:
    """treys suit bitmask (1, 2, 4, 8)."""
    return Card.get_suit_int(card)
