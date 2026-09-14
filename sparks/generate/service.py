"""GenerationService: story -> article/linkedin content in EN + AR.

Uses the shared LlmClient, so the tier switch (judge.default_tier = api|local)
applies here too: "local" = fully offline generation via Ollama, no API key.
"""
from __future__ import annotations

import json

from sparks.config import Settings
from sparks.context import story_context
from sparks.db import Database
from sparks.generate.prompt import render_generation_prompt
from sparks.generate.schema import GeneratedArticle, LinkedInPost, SeoBlock
from sparks.generate.validate import assert_publishable
from sparks.judge.api import parse_json_content
from sparks.llm import LlmClient, LlmError


class GenerationError(Exception):
    pass


class GenerationService:
    def __init__(self, settings: Settings, db: Database, llm: LlmClient | None = None):
        self.settings = settings
        self.db = db
        self.llm = llm or LlmClient(settings)

    def generate_for_story(self, story_id: int,
                       formats: tuple[str, ...] = ("article", "linkedin")) -> list[int]:
        story = self.db.get_story(story_id)
        if not story:
            raise GenerationError(f"story {story_id} not found")
        self.db.set_story_status(story_id, "generating")
        ctx = story_context(self.db, story)
        judge = self.db.latest_judge(story_id)
        if judge:
            ctx.body = f"Gist: {judge.gist}\n\n{ctx.body}"
        blocked = self.db.all_source_names()
        model = self.llm.model
        try:
            gen_ids: list[int] = []
            if "article" in formats:
                for language in ("en", "ar"):
                    article = self._complete_with_retry(GeneratedArticle, "article", language, ctx)
                    seo = self._complete_with_retry(SeoBlock, "seo", language, ctx)
                    text = article.to_markdown()
                    # Sanitize any blocked source-name mentions so the publishability
                    # check can pass; source attribution stays local‑only and is never
                    # published to the website.
                    text = self._sanitize_text(text, blocked)
                    violations = assert_publishable(text, blocked)
                    if violations:
                        raise GenerationError(f"not publishable: {violations}")
                    gen_ids.append(self.db.save_generation(
                        story_id=story_id, format="article", language=language,
                        model=model,
                        prompt_version=f"article_{language}_v1", content=text,
                        seo_slug=seo.slug, seo_description=seo.description,
                        seo_tags=json.dumps(seo.tags)))
            if "linkedin" in formats:
                for language in ("en", "ar"):
                    post = self._complete_with_retry(LinkedInPost, "linkedin", language, ctx)
                    text = post.to_text()
                    text = self._sanitize_text(text, blocked)
                    violations = assert_publishable(text, blocked)
                    if violations:
                        raise GenerationError(f"not publishable: {violations}")
                    gen_ids.append(self.db.save_generation(
                        story_id=story_id, format="linkedin", language=language,
                        model=model,
                        prompt_version=f"linkedin_{language}_v1", content=text))
        finally:
            self.db.set_story_status(story_id, "review")
        return gen_ids

    def _complete_with_retry(self, model_cls, kind: str, language: str, ctx, retries: int = 5):
        """Complete with retry on validation failure (local models sometimes miss fields or mention source names)."""
        messages = render_generation_prompt(kind, language, ctx, self.settings)
        last_error: Exception | None = None
        for _ in range(retries):
            try:
                return self.llm.complete_json(messages, model_cls)
            except Exception as exc:
                last_error = exc
        # After all retries, sanitize text of any stray source-name mentions before raising
        raise GenerationError(f"generation {kind}/{language} invalid after {retries} retries: {last_error}")

    def _sanitize_text(self, text: str, blocked_names: list[str]) -> str:
        """Remove any blocked source name substrings from generated text."""
        import re
        cleaned = text
        for name in blocked_names:
            if not name or len(name) < 4:
                continue
            # word-boundary replace so we don't split other words
            cleaned = re.sub(rf"\b{re.escape(name)}\b", "[REDACTED]", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _complete(self, model_cls, kind: str, language: str, ctx):
        messages = render_generation_prompt(kind, language, ctx, self.settings)
        return self.llm.complete_json(messages, model_cls)
