"""Render generation prompts from versioned templates."""
from __future__ import annotations

import importlib.resources
import pathlib

from sparks.config import Settings
from sparks.judge.schema import StoryContext

_KINDS = {("article", "en"): "article_en_v1", ("article", "ar"): "article_ar_v1",
          ("linkedin", "en"): "linkedin_en_v1", ("linkedin", "ar"): "linkedin_ar_v1",
          ("seo", "en"): "seo_en_v1", ("seo", "ar"): "seo_ar_v1"}


def _load(name: str, settings: Settings | None) -> str:
    if settings and settings.prompts_dir:
        override = pathlib.Path(settings.prompts_dir) / f"{name}.md"
        if override.exists():
            return override.read_text(encoding="utf-8")
    return (importlib.resources.files("sparks") / "prompts" / f"{name}.md"
            ).read_text(encoding="utf-8")


def render_generation_prompt(kind: str, language: str, ctx: StoryContext,
                             settings: Settings | None = None) -> list[dict]:
    template = _load(_KINDS[(kind, language)], settings)
    system_part, _, user_part = template.partition("## USER")
    system_text = system_part.split("## SYSTEM", 1)[-1].strip()
    user_text = user_part.strip()
    for key, value in {"{{TITLE}}": ctx.title, "{{GIST}}": ctx.lead,
                       "{{LEAD}}": ctx.lead, "{{BODY}}": ctx.body[:1500],
                       "{{N_SOURCES}}": str(ctx.n_sources)}.items():
        system_text = system_text.replace(key, value)
        user_text = user_text.replace(key, value)
    return [{"role": "system", "content": system_text},
            {"role": "user", "content": user_text}]
