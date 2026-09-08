"""Local judge tier: Ollama /api/chat on localhost."""
from __future__ import annotations

import httpx

from sparks.config import LocalJudgeConfig, Settings
from sparks.judge.api import parse_json_content
from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext


class OllamaJudge:
    def __init__(self, cfg: LocalJudgeConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=300)  # CPU inference is slow
        return self._client

    def judge(self, ctx: StoryContext, settings: Settings | None = None) -> JudgeOutput:
        messages = render_judge_prompt(ctx, settings=settings)
        payload = {"model": self.cfg.model, "messages": messages, "format": "json",
                   "stream": False, "options": {"temperature": 0.2}}
        last_error: Exception | None = None
        for _ in range(2):
            try:
                resp = self.client.post(f"{self.cfg.ollama_url.rstrip('/')}/api/chat",
                                        json=payload)
                resp.raise_for_status()
                content = resp.json()["message"]["content"]
                return parse_json_content(content, JudgeOutput)
            except JudgeError as exc:
                last_error = exc
            except Exception as exc:
                raise JudgeError(f"ollama judge request failed: {exc}") from exc
        raise JudgeError(f"ollama judge invalid output after retry: {last_error}")
