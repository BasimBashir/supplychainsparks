"""API judge tier: any OpenAI-compatible /chat/completions endpoint."""
from __future__ import annotations

import json
import re

import httpx
from pydantic import BaseModel

from sparks.config import ApiJudgeConfig, Settings
from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def parse_json_content(content: str, model_cls: type[BaseModel]):
    """Parse an LLM reply into the given pydantic model, tolerating fences/noise."""
    text = _FENCE_RE.sub("", content.strip())
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise JudgeError(f"no JSON object in reply: {content[:120]!r}")
    try:
        return model_cls.model_validate(json.loads(text[start:end + 1]))
    except Exception as exc:
        raise JudgeError(f"invalid judge payload: {exc}") from exc


class ApiJudge:
    def __init__(self, cfg: ApiJudgeConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60)
        return self._client

    def judge(self, ctx: StoryContext, settings: Settings | None = None) -> JudgeOutput:
        messages = render_judge_prompt(ctx, settings=settings)
        payload = {"model": self.cfg.model, "messages": messages,
                   "temperature": 0.2, "response_format": {"type": "json_object"}}
        headers = {"authorization": f"Bearer {self.cfg.api_key}"}
        last_error: Exception | None = None
        for _ in range(2):  # one retry on invalid output (spec 11)
            try:
                resp = self.client.post(f"{self.cfg.base_url.rstrip('/')}/chat/completions",
                                        json=payload, headers=headers)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return parse_json_content(content, JudgeOutput)
            except JudgeError as exc:
                last_error = exc
            except Exception as exc:
                raise JudgeError(f"api judge request failed: {exc}") from exc
        raise JudgeError(f"api judge invalid output after retry: {last_error}")
