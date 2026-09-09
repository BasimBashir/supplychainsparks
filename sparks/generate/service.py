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
from sparks.llm import LlmClient


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
                    article = self._complete(GeneratedArticle, "article", language, ctx)
                    seo = self._complete(SeoBlock, "seo", language, ctx)
                    text = article.to_markdown()
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
                    post = self._complete(LinkedInPost, "linkedin", language, ctx)
                    text = post.to_text()
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

    def _complete(self, model_cls, kind: str, language: str, ctx):
        messages = render_generation_prompt(kind, language, ctx, self.settings)
        return self.llm.complete_json(messages, model_cls)
