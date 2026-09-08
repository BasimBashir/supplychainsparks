"""Render the versioned judge prompt. Loads from settings.prompts_dir if set,
else the bundled sparks/prompts/judge_v1.md."""
from __future__ import annotations

import importlib.resources
import pathlib

from sparks.config import Settings
from sparks.judge.schema import CATEGORIES, PROMPT_VERSION, StoryContext

_PLACEHOLDER_SCHEMA_FIELDS = ("supply_chain_relevance, saudi_gcc_relevance, "
                              "market_impact, novelty, rationale_supply_chain, "
                              "rationale_saudi_gcc, rationale_market_impact, "
                              "rationale_novelty, suggested_category, gist")


def _load_template(settings: Settings | None) -> str:
    if settings and settings.prompts_dir:
        override = pathlib.Path(settings.prompts_dir) / f"{PROMPT_VERSION}.md"
        if override.exists():
            return override.read_text(encoding="utf-8")
    return (importlib.resources.files("sparks") / "prompts" / f"{PROMPT_VERSION}.md"
            ).read_text(encoding="utf-8")


def render_judge_prompt(ctx: StoryContext, settings: Settings | None = None) -> list[dict]:
    template = _load_template(settings)
    system_part, _, user_part = template.partition("## USER")
    system_text = system_part.split("## SYSTEM", 1)[-1].strip()
    user_text = user_part.strip()

    replacements = {
        "{{SCHEMA_CATEGORIES}}": ", ".join(CATEGORIES),
        "{{SCHEMA_FIELDS}}": _PLACEHOLDER_SCHEMA_FIELDS,
        "{{TITLE}}": ctx.title,
        "{{LEAD}}": ctx.lead,
        "{{BODY}}": ctx.body[:1500],
        "{{N_SOURCES}}": str(ctx.n_sources),
    }
    for key, value in replacements.items():
        system_text = system_text.replace(key, value)
        user_text = user_text.replace(key, value)
    return [{"role": "system", "content": system_text},
            {"role": "user", "content": user_text}]
