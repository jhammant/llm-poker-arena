"""Load the model roster and build LLM players from config/models.yaml."""
from __future__ import annotations

import os

import yaml

from .llm.client import LLMClient
from .players.llm_player import LLMPlayer

DEFAULT_CONFIG = "config/models.yaml"


def load_config(path: str = DEFAULT_CONFIG) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _entry(cfg: dict, name: str) -> dict:
    for p in cfg["players"]:
        if p["name"] == name:
            return p
    raise KeyError(f"no player named {name!r} in config")


def make_client(cfg: dict, entry: dict) -> LLMClient:
    prov = cfg["providers"][entry["provider"]]
    if "api_key_env" in prov:
        api_key = os.environ.get(prov["api_key_env"], "")
    else:
        api_key = prov.get("api_key", "not-needed")
    d = cfg.get("defaults", {})
    # OpenRouter recommends identifying headers (optional, harmless elsewhere).
    extra_headers = None
    if entry["provider"] == "openrouter":
        extra_headers = {"HTTP-Referer": "https://github.com/local/pokerllm", "X-Title": "pokerllm"}
    return LLMClient(
        base_url=prov["base_url"],
        api_key=api_key,
        model=entry["model"],
        temperature=d.get("temperature", 0.5),
        max_tokens=d.get("max_tokens", 512),
        reasoning_effort=d.get("reasoning_effort"),
        extra_headers=extra_headers,
    )


def make_player(cfg: dict, name: str, system_extra: str | None = None) -> LLMPlayer:
    entry = _entry(cfg, name)
    return LLMPlayer(name, make_client(cfg, entry), system_extra=system_extra)


def enabled_player_names(cfg: dict) -> list[str]:
    return [p["name"] for p in cfg["players"] if p.get("enabled")]
