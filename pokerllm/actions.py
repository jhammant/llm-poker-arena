"""Action types shared by the engine and players."""
from __future__ import annotations

from dataclasses import dataclass

FOLD = "fold"
CHECK = "check"
CALL = "call"
RAISE = "raise"


@dataclass
class Action:
    kind: str
    # For RAISE: the total chips this player will have committed THIS street
    # after the raise (i.e. "raise TO amount"), matching poker convention.
    amount: int = 0
    # Optional free-text reasoning (LLMs fill this in) for logs / dashboard.
    note: str = ""
    # Optional table talk: what the player says to the opponent when acting
    # (default empty = silent).
    talk: str = ""

    def __str__(self) -> str:
        if self.kind == RAISE:
            return f"raise to {self.amount}"
        return self.kind


@dataclass
class LegalActions:
    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int
    can_raise: bool
    min_raise_to: int
    max_raise_to: int

    def describe(self) -> str:
        parts = []
        if self.can_fold:
            parts.append("fold")
        if self.can_check:
            parts.append("check")
        if self.can_call:
            parts.append(f"call {self.call_amount}")
        if self.can_raise:
            parts.append(f"raise to an amount in [{self.min_raise_to}, {self.max_raise_to}]")
        return "; ".join(parts)
