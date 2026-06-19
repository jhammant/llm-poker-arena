"""Player interface. A player maps an Observation to an Action."""
from __future__ import annotations

from ..actions import Action
from ..engine import Observation


class Player:
    name: str = "player"

    def act(self, obs: Observation) -> Action:
        raise NotImplementedError

    def reset(self) -> None:
        """Called at the start of a new session, if the player keeps state."""
