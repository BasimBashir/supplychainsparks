"""FactCheckService: verify generated claims against source material."""
from __future__ import annotations

import importlib.resources

import httpx
from pydantic import BaseModel, field_validator

from sparks.config import Settings
from sparks.db import Database
from sparks.judge.api import parse_json_content


class ClaimList(BaseModel):
    claims: list[dict]

    @field_validator("claims")
    @classmethod
    def _non_empty(cls, v):
        if not isinstance(v, list):
            raise ValueError("claims must be a list")
        return v


class FactCheckService:
    def __init__(self, settings: Settings, db: Database,
                 api_client: httpx.Client | None = None):
        self.settings = settings
        self.db = db
        self._client = api_client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=120)
        return self._client

    def check_generation(self, generation_id: int) -> int:
        gen = self._generation(generation_id)
        story = self.db.get_story(gen["story_id"])
        sources = "\n---\n".join(
            (m.extracted_text or "")[:2000] for m in self.db.story_members(story.id))
        prompt = self._render(gen["content"], sources)
        cfg = self.settings.judge.api
        resp = self.client.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            json={"model": cfg.model, "messages": prompt, "temperature": 0.0},
            headers={"authorization": f"Bearer {cfg.api_key}"})
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        claims = parse_json_content(content, ClaimList).claims
        flags = [c for c in claims if c.get("verdict") != "supported"]
        self.db.replace_fact_flags(generation_id, claims)
        return len(flags)

    def _generation(self, generation_id: int) -> dict:
        row = self.db.conn.execute("SELECT * FROM generations WHERE id=?",
                                   (generation_id,)).fetchone()
        if not row:
            raise ValueError(f"generation {generation_id} not found")
        return dict(row)

    def _render(self, draft: str, sources: str) -> list[dict]:
        template = (importlib.resources.files("sparks") / "prompts" / "factcheck_v1.md"
                    ).read_text(encoding="utf-8")
        system_part, _, user_part = template.partition("## USER")
        system = system_part.split("## SYSTEM", 1)[-1].strip()
        user = user_part.strip().replace("{{DRAFT}}", draft).replace("{{SOURCES}}", sources)
        return [{"role": "system", "content": system},
                {"role": "user", "content": user}]
