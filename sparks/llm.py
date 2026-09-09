"""Shared LLM client: one completion interface over both tiers.

Tier is chosen by settings.judge.default_tier:
- "api"   -> any OpenAI-compatible /chat/completions endpoint (cloud)
- "local" -> Ollama /api/chat on localhost (no API key needed)
Used by generation and fact-check; the judge has its own equivalent tiering.
"""
from __future__ import annotations

import httpx
from pydantic import BaseModel

from sparks.config import Settings
from sparks.judge.api import parse_json_content


class LlmError(Exception):
    pass


class LlmClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    @property
    def tier(self) -> str:
        return "local" if self.settings.judge.default_tier == "local" else "api"

    @property
    def model(self) -> str:
        if self.tier == "local":
            return self.settings.judge.local.model
        return self.settings.judge.api.model

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            timeout = 300 if self.tier == "local" else 120  # CPU inference is slow
            self._client = httpx.Client(timeout=timeout)
        return self._client

    def complete_json(self, messages: list[dict], model_cls: type[BaseModel]):
        """Send chat messages, parse the reply into the given pydantic model."""
        try:
            if self.tier == "local":
                content = self._complete_local(messages)
            else:
                content = self._complete_api(messages)
        except LlmError:
            raise
        except Exception as exc:
            raise LlmError(f"{self.tier} request failed: {exc}") from exc
        return parse_json_content(content, model_cls)

    def _complete_api(self, messages: list[dict]) -> str:
        cfg = self.settings.judge.api
        resp = self.client.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            json={"model": cfg.model, "messages": messages, "temperature": 0.4,
                  "response_format": {"type": "json_object"}},
            headers={"authorization": f"Bearer {cfg.api_key}"})
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _complete_local(self, messages: list[dict]) -> str:
        cfg = self.settings.judge.local
        resp = self.client.post(
            f"{cfg.ollama_url.rstrip('/')}/api/chat",
            json={"model": cfg.model, "messages": messages, "format": "json",
                  "stream": False, "options": {"temperature": 0.4}})
        resp.raise_for_status()
        return resp.json()["message"]["content"]
