"""Pydantic output models for generated content + markdown renderers."""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class GeneratedArticle(BaseModel):
    headline: str
    summary: str
    what_happened: str
    why_it_matters: str
    takeaways: list[str]

    @field_validator("headline", "summary", "what_happened", "why_it_matters")
    @classmethod
    def _no_urls(cls, v: str) -> str:
        if "http" in v or "www." in v:
            raise ValueError("generated content must not contain URLs")
        return v

    def to_markdown(self) -> str:
        lines = [self.headline, "", self.summary, "",
                 "## What happened", "", self.what_happened, "",
                 "## Why it matters", "", self.why_it_matters, "", "## Key takeaways", ""]
        lines += [f"- {t}" for t in self.takeaways]
        return "\n".join(lines)


class LinkedInPost(BaseModel):
    hook: str
    insights: list[str]
    cta: str
    hashtags: list[str]

    def to_text(self) -> str:
        parts = [self.hook, "\n".join(self.insights), self.cta,
                 " ".join(f"#{h.lstrip('#')}" for h in self.hashtags)]
        return "\n\n".join(parts)


class SeoBlock(BaseModel):
    slug: str
    description: str
    tags: list[str]
