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
        self.on_stream = None  # optional (seat, thinking, answer) sink for live streaming
        self.talk = False  # when True, allow/expect table talk in prompts & replies

    def _generate(self, messages, obs):
        if self.on_stream is not None:
            seat = obs.hero
            try:
                return self.client.complete_stream(
                    messages, lambda thinking, answer: self.on_stream(seat, thinking, answer))
            except Exception:  # streaming unsupported / mid-stream failure -> normal call
                return self.client.complete(messages)
        return self.client.complete(messages)

    def act(self, obs):
        messages = build_messages(obs, self.system_extra, talk=self.talk)
        for _ in range(self.retries + 1):
            try:
                text, st = self._generate(messages, obs)
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
