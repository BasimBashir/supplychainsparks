"""Judge output contract: pydantic model, categories, shared error."""
from __future__ import annotations

from pydantic import BaseModel, field_validator

PROMPT_VERSION = "judge_v1"

CATEGORIES = [
    "logistics", "ports-shipping", "warehousing", "procurement", "manufacturing",
    "transport", "e-commerce-logistics", "cold-chain", "technology-automation",
    "trade-policy", "investment", "government-policy", "sustainability", "other",
]


class JudgeError(Exception):
    """Raised when a judge tier fails or returns unparseable/invalid output."""


class StoryContext(BaseModel):
    title: str
    lead: str
    body: str
    n_sources: int = 1


class JudgeOutput(BaseModel):
    supply_chain_relevance: int
    saudi_gcc_relevance: int
    market_impact: int
    novelty: int
    rationale_supply_chain: str
    rationale_saudi_gcc: str
    rationale_market_impact: str
    rationale_novelty: str
    suggested_category: str
    gist: str

    @field_validator("supply_chain_relevance", "saudi_gcc_relevance",
                     "market_impact", "novelty")
    @classmethod
    def _bound_0_10(cls, v: int) -> int:
        if not 0 <= v <= 10:
            raise ValueError("score must be 0-10")
        return v

    @field_validator("suggested_category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        v = (v or "").strip().lower()
        return v if v in CATEGORIES else "other"
