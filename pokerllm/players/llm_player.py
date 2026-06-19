"""An LLM-backed player. Asks the model for a JSON action, with one corrective
retry on a malformed reply; if it still fails, returns None and the engine
sanitises to check/fold (so a flaky model loses pots but never crashes a run)."""
from __future__ import annotations

from ..llm.client import LLMClient, UsageAccumulator
from ..llm.prompt import build_messages, parse_action
from .base import Player


class LLMPlayer(Player):
    def __init__(self, name: str, client: LLMClient, system_extra: str | None = None, retries: int = 1):
        self.name = name
        self.client = client
        self.system_extra = system_extra  # injected strategy "tuition", if any
        self.retries = retries
        self.usage = UsageAccumulator()

    def act(self, obs):
        messages = build_messages(obs, self.system_extra)
        for _ in range(self.retries + 1):
            try:
                text, st = self.client.complete(messages)
            except Exception:
                self.usage.errors += 1
                return None
            self.usage.add(st)
            action = parse_action(text)
            if action is not None:
                return action
            self.usage.parse_failures += 1
            messages.append({"role": "assistant", "content": text[:500]})
            messages.append({
                "role": "user",
                "content": 'That was not valid. Reply with ONLY the JSON object, '
                           'e.g. {"action":"call","amount":0,"reasoning":"..."}',
            })
        return None
