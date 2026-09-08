"""Dataclasses shared across pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Source:
    name: str
    kind: str                      # 'rss' | 'html'
    url: str
    credibility: float = 0.5       # 0.0-1.0 editorial trust weight
    category_hint: str | None = None
    link_pattern: str | None = None
    enabled: bool = True
    healthy: bool = True
    last_fetch_at: datetime | None = None
    id: int | None = None


@dataclass
class FetchedEntry:
    url: str
    title: str
    published_at: datetime | None = None


@dataclass
class ItemRecord:
    id: int
    source_id: int
    url: str
    url_key: str
    title: str | None
    title_key: str | None
    published_at: datetime | None
    fetched_at: datetime
    raw_path: str
    extracted_text: str | None = None
    language: str | None = None
    word_count: int | None = None
    status: str = "new"
    story_id: int | None = None


@dataclass
class StoryRecord:
    id: int
    title: str
    primary_item_id: int
    category: str | None = None
    priority: float | None = None
    band: str | None = None
    status: str = "clustered"      # clustered -> ranked -> selected -> generating -> review -> approved -> published | rejected | archived
    judge_status: str = "none"     # none | api | local | unscored
    n_sources: int = 1
    created_at: datetime | None = None


@dataclass
class JudgeScoreRow:
    story_id: int
    tier: str
    model: str
    prompt_version: str
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
    created_at: datetime | None = None


@dataclass
class SourceRun:
    source_id: int
    source_name: str
    status: str                    # ok | error | skipped_robots
    items_found: int = 0
    items_new: int = 0
    error: str | None = None


@dataclass
class CycleReport:
    started_at: datetime
    finished_at: datetime | None = None
    runs: list[SourceRun] = field(default_factory=list)
    items_new: int = 0
    stories_created: int = 0
    stories_judged: int = 0
    stories_unscored: int = 0
    stories_ranked: int = 0
    errors: list[str] = field(default_factory=list)
