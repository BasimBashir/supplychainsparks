"""GenerationService: story -> article/linkedin content in EN + AR."""
from __future__ import annotations

import json

import httpx

from sparks.config import Settings
from sparks.context import story_context
from sparks.db import Database
from sparks.generate.prompt import render_generation_prompt
from sparks.generate.schema import GeneratedArticle, LinkedInPost, SeoBlock
from sparks.generate.validate import assert_publishable
from sparks.judge.api import parse_json_content


class GenerationError(Exception):
    pass


class GenerationService:
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

    def _complete(self, messages: list[dict]) -> str:
        cfg = self.settings.judge.api
        resp = self.client.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            json={"model": cfg.model, "messages": messages, "temperature": 0.4},
            headers={"authorization": f"Bearer {cfg.api_key}"})
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

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
        try:
            gen_ids: list[int] = []
            if "article" in formats:
                for language in ("en", "ar"):
                    article = parse_json_content(
                        self._complete(render_generation_prompt("article", language, ctx,
                                                                self.settings)),
                        GeneratedArticle)
                    seo = parse_json_content(
                        self._complete(render_generation_prompt("seo", language, ctx,
                                                                self.settings)),
                        SeoBlock)
                    text = article.to_markdown()
                    violations = assert_publishable(text, blocked)
                    if violations:
                        raise GenerationError(f"not publishable: {violations}")
                    gen_ids.append(self.db.save_generation(
                        story_id=story_id, format="article", language=language,
                        model=self.settings.judge.api.model,
                        prompt_version=f"article_{language}_v1", content=text,
                        seo_slug=seo.slug, seo_description=seo.description,
                        seo_tags=json.dumps(seo.tags)))
            if "linkedin" in formats:
                for language in ("en", "ar"):
                    post = parse_json_content(
                        self._complete(render_generation_prompt("linkedin", language, ctx,
                                                                self.settings)),
                        LinkedInPost)
                    text = post.to_text()
                    violations = assert_publishable(text, blocked)
                    if violations:
                        raise GenerationError(f"not publishable: {violations}")
                    gen_ids.append(self.db.save_generation(
                        story_id=story_id, format="linkedin", language=language,
                        model=self.settings.judge.api.model,
                        prompt_version=f"linkedin_{language}_v1", content=text))
        finally:
            self.db.set_story_status(story_id, "review")
        return gen_ids
