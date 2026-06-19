"""OpenAI-compatible client wrapping OpenRouter / LM Studio / Ollama.

All three speak the same chat-completions API, so a model is just
(base_url, api_key, model). We track tokens + latency per call so the report can
show speed and (for paid providers) cost.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from openai import OpenAI


@dataclass
class CallStat:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_s: float = 0.0


@dataclass
class UsageAccumulator:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_latency_s: float = 0.0
    parse_failures: int = 0
    errors: int = 0

    def add(self, st: CallStat) -> None:
        self.calls += 1
        self.prompt_tokens += st.prompt_tokens
        self.completion_tokens += st.completion_tokens
        self.total_latency_s += st.latency_s

    @property
    def avg_latency_s(self) -> float:
        return self.total_latency_s / self.calls if self.calls else 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 512,
        reasoning_effort: str | None = None,
        timeout: float = 180.0,
        extra_headers: dict | None = None,
    ):
        self._client = OpenAI(base_url=base_url, api_key=api_key or "not-needed", timeout=timeout)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort
        self.extra_headers = extra_headers

    def complete(self, messages: list[dict]) -> tuple[str, CallStat]:
        kwargs: dict = dict(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        # reasoning_effort is sent via extra_body so servers that don't support it
        # simply ignore the key rather than 400-ing on an unknown top-level arg.
        if self.reasoning_effort:
            kwargs["extra_body"] = {"reasoning_effort": self.reasoning_effort}

        t0 = time.time()
        resp = self._client.chat.completions.create(**kwargs)
        dt = time.time() - t0

        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        st = CallStat(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_s=dt,
        )
        return text, st

    def complete_stream(self, messages: list[dict], on_token) -> tuple[str, CallStat]:
        """Like complete(), but streams. on_token(thinking, answer) is called as
        tokens arrive (thinking = reasoning channel if the model exposes one,
        answer = the visible content). Returns (final answer text, CallStat)."""
        kwargs: dict = dict(
            model=self.model, messages=messages, temperature=self.temperature,
            max_tokens=self.max_tokens, stream=True,
            stream_options={"include_usage": True},
        )
        if self.extra_headers:
            kwargs["extra_headers"] = self.extra_headers
        if self.reasoning_effort:
            kwargs["extra_body"] = {"reasoning_effort": self.reasoning_effort}

        t0 = time.time()
        think: list[str] = []
        ans: list[str] = []
        usage = None
        for chunk in self._client.chat.completions.create(**kwargs):
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            r = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
            c = getattr(delta, "content", None)
            if r:
                think.append(r)
            if c:
                ans.append(c)
            if r or c:
                on_token("".join(think), "".join(ans))
        dt = time.time() - t0
        st = CallStat(
            prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_s=dt,
        )
        return "".join(ans), st
