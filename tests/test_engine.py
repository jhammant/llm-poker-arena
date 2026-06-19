import random

from treys import Card

from pokerllm import evaluator
from pokerllm.cards import FULL_DECK, shuffled_deck
from pokerllm.engine import play_hand
from pokerllm.match import play_session
from pokerllm.players.heuristic import HeuristicPlayer
from pokerllm.players.random_player import RandomPlayer


def test_deck_is_52_unique():
    assert len(set(FULL_DECK)) == 52


def test_evaluator_orders_hands():
    # Royal flush should beat a pair of aces on the same board.
    board = [Card.new(c) for c in ["Ah", "Kh", "Qh", "2c", "3d"]]
    royal = [Card.new("Jh"), Card.new("Th")]
    pair = [Card.new("Ad"), Card.new("Ac")]
    assert evaluator.evaluate(board, royal) < evaluator.evaluate(board, pair)


def test_chips_are_conserved():
    rng = random.Random(0)
    for _ in range(300):
        deck = shuffled_deck(rng)
        res = play_hand(
            [RandomPlayer(seed=1, aggression=0.4), RandomPlayer(seed=2, aggression=0.4)],
            [200, 200], button=rng.randint(0, 1), big_blind=2, small_blind=1, deck=deck,
        )
        assert sum(res.deltas) == 0
        assert res.deltas[0] >= -200 and res.deltas[1] >= -200  # can't lose more than the stack


def test_duplicate_session_is_zero_sum():
    rng = random.Random(11)
    res = play_session(RandomPlayer("a", seed=1), RandomPlayer("b", seed=2),
                       n_hands=200, starting_stack=200, sb=1, bb=2, rng=rng, duplicate=True)
    assert res.chips[0] == -res.chips[1]


def test_heuristic_beats_random():
    # The whole pipeline: heuristic should be clearly profitable vs random over a
    # large duplicated sample.
    rng = random.Random(7)
    res = play_session(HeuristicPlayer("h"), RandomPlayer("r", seed=3),
                       n_hands=1500, starting_stack=200, sb=1, bb=2, rng=rng, duplicate=True)
    assert res.chips[0] > 0, f"heuristic should beat random, got {res.chips}"
