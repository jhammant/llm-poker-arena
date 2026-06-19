"""Heads-up No-Limit Texas Hold'em engine.

Two seats (0 and 1). The button posts the small blind and acts first preflop,
last postflop (standard heads-up rule). Pure logic: each player is a callable
``act(observation) -> Action``. No network and no globals; a hand is fully
deterministic given the deck and the players' actions.

The engine is defensive: any malformed / illegal action a player returns is
sanitised to the closest legal action (check > call > fold), so a misbehaving
LLM can never crash a tournament.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import evaluator
from .actions import CALL, CHECK, FOLD, RAISE, Action, LegalActions
from .cards import cards_str

STREETS = ["preflop", "flop", "turn", "river"]


class EngineError(Exception):
    pass


@dataclass
class Observation:
    """Everything the player to act can see."""

    hero: int  # seat to act (0 or 1)
    button: int
    street: str
    hole: list[int]
    board: list[int]
    pot: int  # total chips committed by both players so far this hand
    to_call: int
    stacks: list[int]  # chips remaining behind, by seat
    committed: list[int]  # total committed this hand, by seat
    street_committed: list[int]  # committed on the current street, by seat
    big_blind: int
    small_blind: int
    legal: LegalActions
    history: list  # list of (street, seat, Action) so far

    def hero_str(self) -> str:
        return cards_str(self.hole)


@dataclass
class HandResult:
    deltas: list[int]  # chip change per seat (sums to 0)
    button: int
    board: list[int]
    holes: list[list[int]]
    won_by_fold: bool
    showdown: bool
    pot: int
    actions: list = field(default_factory=list)  # structured action log
    note: str = ""


class HandEngine:
    def __init__(
        self,
        players: list,
        stacks: list[int],
        button: int,
        big_blind: int,
        small_blind: int,
        deck: list[int],
        on_event: Optional[Callable[[dict], None]] = None,
    ):
        self.players = players  # [seat0, seat1]; each has .act(obs) -> Action
        self.start_stacks = list(stacks)
        self.stacks = list(stacks)
        self.button = button
        self.bb = big_blind
        self.sb = small_blind
        self.deck = list(deck)
        self.on_event = on_event or (lambda e: None)

        self.committed = [0, 0]
        self.street_committed = [0, 0]
        self.folded = [False, False]
        self.allin = [False, False]
        self.hole: list[list[int]] = [[], []]
        self.board: list[int] = []
        self.history: list = []
        self.actions: list = []
        self.last_raise = big_blind  # minimum raise increment
        self.street = "preflop"

    # ------------------------------------------------------------------ utils
    def _emit(self, etype: str, **data) -> None:
        self.on_event({"type": etype, **data})

    def _post(self, seat: int, amount: int) -> int:
        amt = min(amount, self.stacks[seat])
        self.stacks[seat] -= amt
        self.committed[seat] += amt
        self.street_committed[seat] += amt
        if self.stacks[seat] == 0:
            self.allin[seat] = True
        return amt

    @property
    def pot(self) -> int:
        return sum(self.committed)

    def _street_max(self) -> int:
        return max(self.street_committed)

    def _num_in(self) -> int:
        return sum(1 for f in self.folded if not f)

    # ----------------------------------------------------------- legal actions
    def legal_actions(self, seat: int) -> LegalActions:
        to_call = min(self._street_max() - self.street_committed[seat], self.stacks[seat])
        can_check = to_call == 0
        can_call = to_call > 0
        can_raise = self.stacks[seat] > to_call  # chips left beyond a call
        max_raise_to = self.street_committed[seat] + self.stacks[seat]  # all-in
        min_raise_to = self._street_max() + self.last_raise
        if min_raise_to > max_raise_to:
            # not enough for a full min-raise; only an all-in (short) raise possible
            min_raise_to = max_raise_to
        if not can_raise:
            min_raise_to = max_raise_to = 0
        return LegalActions(
            can_fold=True,
            can_check=can_check,
            can_call=can_call,
            call_amount=to_call,
            can_raise=can_raise,
            min_raise_to=min_raise_to,
            max_raise_to=max_raise_to,
        )

    def _observation(self, seat: int, legal: LegalActions) -> Observation:
        return Observation(
            hero=seat,
            button=self.button,
            street=self.street,
            hole=list(self.hole[seat]),
            board=list(self.board),
            pot=self.pot,
            to_call=legal.call_amount,
            stacks=list(self.stacks),
            committed=list(self.committed),
            street_committed=list(self.street_committed),
            big_blind=self.bb,
            small_blind=self.sb,
            legal=legal,
            history=list(self.history),
        )

    # --------------------------------------------------------- get/apply action
    def _get_action(self, seat: int, legal: LegalActions) -> Action:
        obs = self._observation(seat, legal)
        try:
            action = self.players[seat].act(obs)
        except Exception as e:  # never let a player crash the hand
            self._emit("error", seat=seat, error=repr(e))
            action = None
        return self._sanitize(action, legal)

    @staticmethod
    def _sanitize(action: Optional[Action], legal: LegalActions) -> Action:
        """Coerce any player output into a legal action: check > call > fold."""
        note = action.note if action else ""
        if action is None or action.kind not in (FOLD, CHECK, CALL, RAISE):
            return Action(CHECK, note=note) if legal.can_check else Action(FOLD, note=note)
        if action.kind == FOLD:
            return Action(FOLD, note=note)
        if action.kind == CHECK:
            if legal.can_check:
                return action
            return Action(CALL, note=note) if legal.can_call else Action(FOLD, note=note)
        if action.kind == CALL:
            if legal.can_call:
                return action
            return Action(CHECK, note=note) if legal.can_check else Action(FOLD, note=note)
        # RAISE
        if not legal.can_raise:
            if legal.can_call:
                return Action(CALL, note=note)
            return Action(CHECK, note=note) if legal.can_check else Action(FOLD, note=note)
        amt = max(legal.min_raise_to, min(action.amount, legal.max_raise_to))
        return Action(RAISE, amt, note=note)

    def _apply(self, seat: int, action: Action, legal: LegalActions) -> None:
        if action.kind == FOLD:
            self.folded[seat] = True
        elif action.kind == CHECK:
            pass
        elif action.kind == CALL:
            self._post(seat, legal.call_amount)
        elif action.kind == RAISE:
            inc = action.amount - self._street_max()
            self._post(seat, action.amount - self.street_committed[seat])
            if inc >= self.last_raise:  # only full raises reset the min-raise size
                self.last_raise = inc
        self.history.append((self.street, seat, action))
        self.actions.append(
            {
                "street": self.street,
                "seat": seat,
                "action": action.kind,
                "amount": action.amount,
                "note": action.note,
                "pot": self.pot,
                "to_call": legal.call_amount,
            }
        )
        self._emit(
            "action",
            street=self.street,
            seat=seat,
            action=action.kind,
            amount=action.amount,
            note=action.note,
            pot=self.pot,
            stacks=list(self.stacks),
        )

    # ------------------------------------------------------------ betting round
    def _betting_round(self, first: int) -> None:
        order = deque([first, 1 - first])
        while order:
            seat = order.popleft()
            if self.folded[seat] or self.allin[seat]:
                continue
            if self._num_in() <= 1:
                return
            legal = self.legal_actions(seat)
            prev_max = self._street_max()
            action = self._get_action(seat, legal)
            self._apply(seat, action, legal)
            if action.kind == RAISE and self._street_max() > prev_max:
                opp = 1 - seat
                # any bet increase reopens action for the (only) opponent
                order = deque([opp]) if not (self.folded[opp] or self.allin[opp]) else deque()

    # -------------------------------------------------------------------- play
    def play(self) -> HandResult:
        # Deal hole cards (seat0 gets deck[0], deck[2]; seat1 gets deck[1], deck[3]).
        self.hole[0] = [self.deck[0], self.deck[2]]
        self.hole[1] = [self.deck[1], self.deck[3]]
        flop = [self.deck[4], self.deck[5], self.deck[6]]
        turn = self.deck[7]
        river = self.deck[8]

        # Blinds: heads-up button posts the small blind.
        sb_seat = self.button
        bb_seat = 1 - self.button
        self._post(sb_seat, self.sb)
        self._post(bb_seat, self.bb)
        self.last_raise = self.bb
        self._emit(
            "hand_start",
            button=self.button,
            sb=self.sb,
            bb=self.bb,
            holes=[cards_str(self.hole[0]), cards_str(self.hole[1])],
        )

        for street in STREETS:
            self.street = street
            if street != "preflop":
                self.street_committed = [0, 0]
                self.last_raise = self.bb
                if street == "flop":
                    self.board = list(flop)
                elif street == "turn":
                    self.board.append(turn)
                elif street == "river":
                    self.board.append(river)
                self._emit("board", street=street, board=cards_str(self.board))

            first = self.button if street == "preflop" else (1 - self.button)
            # Once anyone is all-in, all bets are already matched — just run the
            # board out without further betting.
            if self._num_in() > 1 and not self.allin[0] and not self.allin[1]:
                self._betting_round(first)
            if self._num_in() <= 1:
                break

        return self._settle()

    def _settle(self) -> HandResult:
        # Refund any uncalled chips (heads-up: the larger contributor gets the
        # difference back before the pot is awarded).
        c0, c1 = self.committed
        if c0 > c1:
            self.stacks[0] += c0 - c1
            self.committed[0] = c1
        elif c1 > c0:
            self.stacks[1] += c1 - c0
            self.committed[1] = c0

        pot = sum(self.committed)
        won_by_fold = self._num_in() <= 1
        showdown = False

        if won_by_fold:
            winner = 0 if not self.folded[0] else 1
            self.stacks[winner] += pot
            note = f"seat {winner} wins {pot} (opponent folded)"
        else:
            showdown = True
            s0 = evaluator.evaluate(self.board, self.hole[0])
            s1 = evaluator.evaluate(self.board, self.hole[1])
            if s0 < s1:
                self.stacks[0] += pot
                note = f"seat 0 wins {pot} at showdown"
            elif s1 < s0:
                self.stacks[1] += pot
                note = f"seat 1 wins {pot} at showdown"
            else:
                half = pot // 2
                self.stacks[0] += half
                self.stacks[1] += pot - half  # odd chip to seat 1
                note = f"split pot {pot}"

        deltas = [self.stacks[i] - self.start_stacks[i] for i in (0, 1)]
        self._emit(
            "result",
            deltas=deltas,
            pot=pot,
            showdown=showdown,
            board=cards_str(self.board),
            holes=[cards_str(self.hole[0]), cards_str(self.hole[1])],
            note=note,
        )
        return HandResult(
            deltas=deltas,
            button=self.button,
            board=list(self.board),
            holes=[list(self.hole[0]), list(self.hole[1])],
            won_by_fold=won_by_fold,
            showdown=showdown,
            pot=pot,
            actions=self.actions,
            note=note,
        )


def play_hand(
    players: list,
    stacks: list[int],
    button: int,
    big_blind: int,
    small_blind: int,
    deck: list[int],
    on_event: Optional[Callable[[dict], None]] = None,
) -> HandResult:
    """Convenience wrapper: play one hand and return the result."""
    return HandEngine(players, stacks, button, big_blind, small_blind, deck, on_event).play()
