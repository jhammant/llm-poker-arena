"""Sessions between two players.

A session is many hands with an alternating button. With ``duplicate=True`` each
logical hand is played twice on the *same* shuffled deck with the seats swapped,
and the two results are netted — this cancels the luck of the deal (duplicate
poker) so far fewer hands are needed for trustworthy BB/100 and Elo.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from .cards import shuffled_deck
from .engine import play_hand


@dataclass
class SessionResult:
    names: tuple[str, str]  # (player A, player B)
    hands: int
    chips: list[int]  # net chips, index 0 == A, 1 == B (sums to 0)
    bb_deltas: list[float]  # per logical hand, A's delta in big blinds
    big_blind: int


def play_session(
    p_a,
    p_b,
    n_hands: int,
    starting_stack: int,
    sb: int,
    bb: int,
    rng: random.Random,
    duplicate: bool = True,
    on_event=None,
) -> SessionResult:
    a_bb_deltas: list[float] = []
    for hand_no in range(n_hands):
        button = hand_no % 2  # alternate the button
        deck = shuffled_deck(rng)

        # Pass 1: A at seat 0, B at seat 1.
        res1 = play_hand([p_a, p_b], [starting_stack, starting_stack], button, bb, sb, deck, on_event)
        d_a = res1.deltas[0]

        if duplicate:
            # Pass 2: same deck, seats swapped (B at seat 0, A at seat 1).
            res2 = play_hand([p_b, p_a], [starting_stack, starting_stack], button, bb, sb, deck, on_event)
            d_a += res2.deltas[1]  # A is now seat 1

        a_bb_deltas.append(d_a / bb)

    total_a = int(round(sum(a_bb_deltas) * bb))
    return SessionResult(
        names=(p_a.name, p_b.name),
        hands=n_hands,
        chips=[total_a, -total_a],
        bb_deltas=a_bb_deltas,
        big_blind=bb,
    )
