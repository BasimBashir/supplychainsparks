"""Shared story -> LLM context assembly."""
from __future__ import annotations

import re

from sparks.db import Database
from sparks.judge.schema import StoryContext
from sparks.models import StoryRecord

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def story_context(db: Database, story: StoryRecord) -> StoryContext:
    members = db.story_members(story.id)
    primary = next((m for m in members if m.id == story.primary_item_id), members[0])
    text = (primary.extracted_text or "").strip()
    sentences = _SENTENCE_RE.split(text)
    lead = " ".join(sentences[:2])[:400]
    body = text[len(lead):].strip() if len(text) > len(lead) else text
    return StoryContext(title=primary.title or story.title, lead=lead, body=body,
                        n_sources=max(1, len(members)))
