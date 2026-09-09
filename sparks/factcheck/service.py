"""FactCheckService: verify generated claims against source material.

Uses the shared LlmClient, so the tier switch (judge.default_tier = api|local)
applies here too.
"""
from __future__ import annotations

import importlib.resources

from pydantic import BaseModel, field_validator

from sparks.config import Settings
from sparks.db import Database
from sparks.judge.api import parse_json_content
from sparks.llm import LlmClient


class ClaimList(BaseModel):
    claims: list[dict]

    @field_validator("claims")
    @classmethod
    def _non_empty(cls, v):
        if not isinstance(v, list):
            raise ValueError("claims must be a list")
        return v


class FactCheckService:
    def __init__(self, settings: Settings, db: Database, llm: LlmClient | None = None):
        self.settings = settings
        self.db = db
        self.llm = llm or LlmClient(settings)

    def check_generation(self, generation_id: int) -> int:
        gen = self._generation(generation_id)
        story = self.db.get_story(gen["story_id"])
        sources = "\n---\n".join(
            (m.extracted_text or "")[:2000] for m in self.db.story_members(story.id))
        prompt = self._render(gen["content"], sources)
        claims = self.llm.complete_json(prompt, ClaimList).claims
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
