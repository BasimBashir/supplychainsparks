# Supply Chain Sparks — Plan 1: Pipeline Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the `sparks` Python package — the local pipeline that fetches supply-chain news, extracts and dedupes it, scores it with an LLM-judge, ranks it into an editorial queue, and exposes it via a CLI.

**Architecture:** Deterministic pipeline (fetch → extract → cluster → judge → rank) persisting to SQLite + raw files, fully re-derivable from raw. The LLM-judge has two interchangeable tiers behind one interface: OpenAI-compatible API (default) and local Ollama (fallback). The engine is headless; the dashboard app (Plan 2) and Next.js site (Plan 3) build on these interfaces.

**Tech Stack:** Python 3.11+, httpx, feedparser, trafilatura, rapidfuzz, pydantic v2, PyYAML, sqlite3 (stdlib). Dev: pytest, respx.

**Spec:** `docs/superpowers/specs/2026-09-08-supply-chain-sparks-design.md`

## Global Constraints

- Target machine: Windows 10/11, CPU-only, **8 GB RAM floor**; the engine must never *require* Ollama or any network service at import time.
- Python >= 3.11. Dependencies allowed: `httpx, feedparser, trafilatura, rapidfuzz, pydantic>=2, PyYAML` (+ `pytest, respx` in dev). Nothing else without amending this plan.
- **No network access in automated tests** — fixtures and respx mocks only.
- Monorepo layout: Python package `sparks/` at repo root. The app shell and `site/` come in Plans 2–3.
- Data directory default: `%LOCALAPPDATA%/SupplyChainSparks` on Windows, `~/.local/share/supplychainsparks` elsewhere — never inside the repo. Env overrides: `SPARKS_HOME` (data dir), `SPARKS_SETTINGS` (settings file path).
- Raw files are saved **before** any processing; the DB must remain re-derivable from raw files (the `replay` command proves it).
- No regex/keyword logic may ever decide *relevance* — relevance judgment belongs to the LLM-judge only. (Mechanical plumbing — URL normalization, link extraction, word counts — is allowed.)
- TDD: red → green → commit for every task. Commit messages: `feat|fix|test|chore: ...`.
- All datetimes are timezone-aware UTC ISO-8601 strings in the DB; `datetime.now(timezone.utc)` in code.

## File Structure

```
supplychainsparks/                  # repo root
├── pyproject.toml                  # package metadata, deps, `sparks` CLI entry point
├── settings.yaml                   # default config (committed)
├── sources.yaml                    # seed source registry (committed)
├── .gitignore                      # .venv/, data/, secrets.yaml, __pycache__/, dist/, build/
├── sparks/                         # the engine package
│   ├── __init__.py                 # __version__
│   ├── config.py                   # Settings dataclasses, load_settings(), env resolution
│   ├── models.py                   # Source, FetchedEntry, ItemRecord, StoryRecord, JudgeScoreRow, SourceRun, CycleReport
│   ├── db.py                       # Database: schema, migrations, repository methods
│   ├── extract.py                  # trafilatura extraction + noise filter
│   ├── dedupe.py                   # normalize_url, title_key, simhash, build_clusters (union-find)
│   ├── rank.py                     # compute_priority(), band_for()
│   ├── pipeline.py                 # run_cycle(), replay()
│   ├── cli.py                      # argparse CLI: init/fetch/queue/replay/sources
│   ├── prompts/
│   │   └── judge_v1.md             # versioned judge prompt with few-shot anchors (package data)
│   ├── fetch/
│   │   ├── __init__.py
│   │   ├── rss.py                  # parse_feed(), google_news_query_url()
│   │   ├── html.py                 # parse_listing()
│   │   └── runner.py               # FetchRunner (politeness, robots, raw saving, fetch_runs)
│   └── judge/
│       ├── __init__.py
│       ├── schema.py               # CATEGORIES, StoryContext, JudgeOutput, JudgeError
│       ├── prompt.py               # render_judge_prompt() (loads judge_v1.md, override dir)
│       ├── api.py                  # ApiJudge (OpenAI-compatible chat completions)
│       ├── local.py                # OllamaJudge (localhost /api/chat)
│       └── service.py              # JudgeService (tiering, fallback, unscored marking)
├── tests/
│   ├── conftest.py                 # tmp settings fixture, freeze time helper
│   ├── fixtures/
│   │   ├── rss_basic.xml
│   │   ├── rss_google_news.xml
│   │   ├── html_listing.html
│   │   ├── article_good.html
│   │   ├── article_short.html
│   │   └── article_variant.html    # near-duplicate body of article_good.html
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_fetch_rss.py
│   ├── test_fetch_html.py
│   ├── test_fetch_runner.py
│   ├── test_extract.py
│   ├── test_dedupe.py
│   ├── test_judge_schema.py
│   ├── test_judge_prompt.py
│   ├── test_judge_clients.py
│   ├── test_judge_service.py
│   ├── test_rank.py
│   ├── test_pipeline.py
│   └── test_cli.py
└── docs/superpowers/{specs,plans}/
```

**Interface contract (used across tasks — keep names exact):**

- `sparks.config.load_settings(path=None) -> Settings`; `Settings` has `.data_dir: Path`, `.db_path`, `.raw_dir`, `.settings_path`, `.prompts_dir: Path | None`, `.fetch: FetchConfig`, `.judge: JudgeConfig`, `.rank: RankConfig`
- `sparks.db.Database(path)` with methods listed in Task 2
- `sparks.models`: `Source, FetchedEntry(url, title, published_at), ItemRecord, StoryRecord, JudgeScoreRow, SourceRun, CycleReport`
- `sparks.fetch.rss.parse_feed(data, max_items) -> list[FetchedEntry]`; `google_news_query_url(query, language="en") -> str`
- `sparks.fetch.html.parse_listing(html_text, base_url, link_pattern, max_items) -> list[FetchedEntry]`
- `sparks.fetch.runner.FetchRunner(settings, db, client=None).run(sources=None) -> list[SourceRun]`
- `sparks.extract.extract_article(html_text) -> ExtractedText | None`
- `sparks.dedupe.build_clusters(items, window_days=7) -> list[ClusterDecision]`
- `sparks.judge.schema`: `CATEGORIES`, `StoryContext(title, lead, body, n_sources)`, `JudgeOutput` (pydantic), `JudgeError`, `PROMPT_VERSION`
- `sparks.judge.api.ApiJudge(cfg, client=None).judge(ctx) -> JudgeOutput`; `sparks.judge.local.OllamaJudge(cfg, client=None).judge(ctx) -> JudgeOutput`
- `sparks.judge.service.JudgeService(settings, db, api_judge=None, local_judge=None).judge_pending(limit=None) -> tuple[int, int]`
- `sparks.rank.compute_priority(sc, saudi, impact, novelty, n_sources, credibility, age_hours, cfg) -> float`; `band_for(priority, cfg) -> str`
- `sparks.pipeline.run_cycle(settings, db=None) -> CycleReport`; `sparks.pipeline.replay(settings, skip_judge=False) -> CycleReport`
- `sparks.cli.main(argv=None) -> int`

---

### Task 1: Project scaffold + configuration

**Files:**
- Create: `pyproject.toml`, `settings.yaml`, `sources.yaml`, `.gitignore`, `sparks/__init__.py`, `sparks/config.py`
- Test: `tests/conftest.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `load_settings(path=None) -> Settings` and all config dataclasses below — every later task reads config through these.

- [ ] **Step 1: Create scaffold files**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "supplychainsparks"
version = "0.1.0"
description = "Supply Chain Sparks - supply chain intelligence pipeline for Saudi Arabia / GCC"
requires-python = ">=3.11"
dependencies = [
    "httpx>=0.27",
    "feedparser>=6.0.11",
    "trafilatura>=1.12",
    "rapidfuzz>=3.6",
    "pydantic>=2.7",
    "PyYAML>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "respx>=0.21"]

[project.scripts]
sparks = "sparks.cli:main"

[tool.setuptools.packages.find]
include = ["sparks*"]

[tool.setuptools.package-data]
sparks = ["prompts/*.md"]
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
data/
secrets.yaml
dist/
build/
*.spec
.pytest_cache/
```

`sparks/__init__.py`:

```python
__version__ = "0.1.0"
```

`settings.yaml` (committed defaults; users may copy to a private location and point `SPARKS_SETTINGS` at it):

```yaml
# Supply Chain Sparks defaults. Override by copying this file and setting
# the SPARKS_SETTINGS env var to the copy's path.
fetch:
  user_agent: "SupplyChainSparksBot/0.1 (+https://supplychainsparks.com)"
  per_domain_delay_seconds: 3
  timeout_seconds: 20
  max_items_per_source: 50

judge:
  default_tier: api            # api | local
  api:
    base_url: "https://open.bigmodel.cn/api/paas/v4"   # any OpenAI-compatible endpoint
    model: "glm-4-flash"
    api_key: "env:SPARKS_API_KEY"                       # env:VARNAME resolves at load
  local:
    enabled: true
    ollama_url: "http://localhost:11434"
    model: "qwen2.5:3b"

rank:
  weights: {sc: 0.35, saudi: 0.30, impact: 0.25, novelty: 0.10}
  rubric_scale: 7.0
  corroboration_points: 4.0
  corroboration_cap: 3          # max extra sources that earn points
  credibility_points: 6.0
  recency_points: 12.0
  recency_halflife_hours: 24.0
  high_band: 75.0
  medium_band: 50.0

prompts_dir: null               # optional absolute dir overriding bundled prompts
```

`sources.yaml` (seed registry loaded by `sparks init`, Task 13):

```yaml
# kind: rss  -> url is a feed URL. kind: html -> url is a listing page; link_pattern
# is a regex the href must match (re.search) to count as an article link.
sources:
  - name: Google News - Saudi logistics
    kind: rss
    url: "https://news.google.com/rss/search?q=%22Saudi%22%20%22logistics%22&hl=en-US&gl=US&ceid=US:en"
    credibility: 0.6
    category_hint: logistics
  - name: Google News - Saudi ports
    kind: rss
    url: "https://news.google.com/rss/search?q=%22Saudi%22%20port%20OR%20Jeddah%20OR%20Dammam&hl=en-US&gl=US&ceid=US:en"
    credibility: 0.6
    category_hint: ports-shipping
  - name: Google News - GCC supply chain
    kind: rss
    url: "https://news.google.com/rss/search?q=%22supply%20chain%22%20GCC%20OR%20UAE%20OR%20Qatar&hl=en-US&gl=US&ceid=US:en"
    credibility: 0.6
    category_hint: trade-policy
  - name: Google News - Red Sea shipping
    kind: rss
    url: "https://news.google.com/rss/search?q=%22Red%20Sea%22%20shipping&hl=en-US&gl=US&ceid=US:en"
    credibility: 0.6
    category_hint: ports-shipping
  - name: Google News - Saudi warehousing
    kind: rss
    url: "https://news.google.com/rss/search?q=Saudi%20warehouse%20OR%20warehousing%20OR%20%22free%20zones%22&hl=en-US&gl=US&ceid=US:en"
    credibility: 0.6
    category_hint: warehousing
  - name: Supply Chain Digest
    kind: rss
    url: "https://www.scdigest.com/rss.xml"
    credibility: 0.8
    category_hint: null
  - name: Logistics Middle East
    kind: rss
    url: "https://www.logisticsmiddleeast.com/rss/feed"
    credibility: 0.7
    category_hint: null
  - name: Arab News - Business
    kind: rss
    url: "https://www.arabnews.com/business/rss.xml"
    credibility: 0.7
    category_hint: null
  - name: Gulf News - Transport
    kind: rss
    url: "https://gulfnews.com/rss?generatorName=transport"
    credibility: 0.7
    category_hint: transport
  - name: Mawani press releases
    kind: html
    url: "https://mawani.gov.sa/en/media-center/press-releases"
    link_pattern: "press-release"
    credibility: 0.9
    category_hint: ports-shipping
```

- [ ] **Step 2: Write the failing tests**

`tests/conftest.py`:

```python
import pathlib

import pytest

from sparks.config import load_settings


@pytest.fixture
def settings_path(tmp_path, monkeypatch) -> pathlib.Path:
    """Point the engine at an isolated data dir + settings file."""
    path = tmp_path / "settings.yaml"
    path.write_text("judge:\n  default_tier: local\n", encoding="utf-8")
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("SPARKS_SETTINGS", str(path))
    return path


@pytest.fixture
def settings(settings_path):
    return load_settings(settings_path)
```

`tests/test_config.py`:

```python
import pytest

from sparks.config import load_settings


def repo_settings_path():
    import pathlib
    return pathlib.Path(__file__).parents[2] / "settings.yaml"


def test_defaults_from_bundled_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path))
    s = load_settings(repo_settings_path())
    assert s.fetch.per_domain_delay_seconds == 3
    assert s.judge.default_tier == "api"
    assert s.judge.local.model == "qwen2.5:3b"
    assert s.rank.weights.sc == pytest.approx(0.35)
    assert s.rank.high_band == 75.0
    assert (tmp_path / "SupplyChainSparks.db") == s.db_path or s.db_path.name == "SupplyChainSparks.db"
    assert s.db_path.parent == tmp_path


def test_user_yaml_overrides_defaults(settings):
    assert settings.judge.default_tier == "local"  # from conftest fixture yaml


def test_env_placeholder_resolves_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_TEST_KEY", "sk-test-123")
    p = tmp_path / "s.yaml"
    p.write_text("judge:\n  api:\n    api_key: env:SPARKS_TEST_KEY\n", encoding="utf-8")
    s = load_settings(p)
    assert s.judge.api.api_key == "sk-test-123"


def test_missing_settings_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.yaml")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks'` (or collection error).

- [ ] **Step 4: Implement `sparks/config.py`**

```python
"""Configuration loading: bundled defaults <- user yaml <- env vars."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLED_SETTINGS = REPO_ROOT / "settings.yaml"


@dataclass
class FetchConfig:
    user_agent: str = "SupplyChainSparksBot/0.1"
    per_domain_delay_seconds: float = 3.0
    timeout_seconds: int = 20
    max_items_per_source: int = 50


@dataclass
class ApiJudgeConfig:
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model: str = "glm-4-flash"
    api_key: str = ""


@dataclass
class LocalJudgeConfig:
    enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"


@dataclass
class JudgeConfig:
    default_tier: str = "api"
    api: ApiJudgeConfig = field(default_factory=ApiJudgeConfig)
    local: LocalJudgeConfig = field(default_factory=LocalJudgeConfig)


@dataclass
class RankWeights:
    sc: float = 0.35
    saudi: float = 0.30
    impact: float = 0.25
    novelty: float = 0.10


@dataclass
class RankConfig:
    weights: RankWeights = field(default_factory=RankWeights)
    rubric_scale: float = 7.0
    corroboration_points: float = 4.0
    corroboration_cap: int = 3
    credibility_points: float = 6.0
    recency_points: float = 12.0
    recency_halflife_hours: float = 24.0
    high_band: float = 75.0
    medium_band: float = 50.0


@dataclass
class Settings:
    settings_path: pathlib.Path
    data_dir: pathlib.Path
    prompts_dir: pathlib.Path | None = None
    fetch: FetchConfig = field(default_factory=FetchConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    rank: RankConfig = field(default_factory=RankConfig)

    @property
    def db_path(self) -> pathlib.Path:
        return self.data_dir / "SupplyChainSparks.db"

    @property
    def raw_dir(self) -> pathlib.Path:
        return self.data_dir / "raw"


def _resolve_env(value: Any) -> Any:
    """Resolve strings of the form 'env:VARNAME' from the environment."""
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], "")
    return value


def _merge(dataclass_obj: Any, data: dict) -> None:
    for key, value in data.items():
        value = _resolve_env(value)
        current = getattr(dataclass_obj, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge(current, value)
        else:
            setattr(dataclass_obj, key, value)


def _default_data_dir() -> pathlib.Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA") or str(pathlib.Path.home() / "AppData" / "Local")
        return pathlib.Path(local_app_data) / "SupplyChainSparks"
    return pathlib.Path.home() / ".local" / "share" / "supplychainsparks"


def load_settings(path: pathlib.Path | str | None = None) -> Settings:
    if path is None:
        env_path = os.environ.get("SPARKS_SETTINGS")
        path = pathlib.Path(env_path) if env_path else BUNDLED_SETTINGS
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"settings file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    env_home = os.environ.get("SPARKS_HOME")
    data_dir = pathlib.Path(env_home) if env_home else _default_data_dir()

    prompts_dir = raw.get("prompts_dir")
    settings = Settings(
        settings_path=path,
        data_dir=data_dir,
        prompts_dir=pathlib.Path(prompts_dir) if prompts_dir else None,
    )
    if isinstance(raw.get("fetch"), dict):
        _merge(settings.fetch, raw["fetch"])
    if isinstance(raw.get("judge"), dict):
        _merge(settings.judge, raw["judge"])
    if isinstance(raw.get("rank"), dict):
        _merge(settings.rank, raw["rank"])
    return settings
```

- [ ] **Step 5: Create the venv, install, run tests**

```bash
python -m venv .venv
. .venv/Scripts/activate   # Windows (Git Bash: source .venv/Scripts/activate)
pip install -e ".[dev]"
python -m pytest tests/test_config.py -v
```

Expected: 4 PASSED.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml settings.yaml sources.yaml .gitignore sparks/ tests/
git commit -m "feat: project scaffold and settings loader"
```

---

### Task 2: Models + SQLite layer

**Files:**
- Create: `sparks/models.py`, `sparks/db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Settings` from Task 1 (`settings.db_path`).
- Produces: `Database` (below) and the record dataclasses — used by fetcher, judge, rank, pipeline, CLI tasks.

- [ ] **Step 1: Write the failing tests**

`tests/test_db.py`:

```python
from datetime import datetime, timezone

import pytest

from sparks.db import Database
from sparks.models import FetchedEntry, JudgeOutput, Source

NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _source(db, name="Test Feed", credibility=0.5):
    return db.upsert_source(Source(
        name=name, kind="rss", url=f"https://example.com/{name.replace(' ', '-')}",
        credibility=credibility,
    ))


def test_upsert_source_is_idempotent(db):
    sid1 = db.upsert_source(Source(name="A", kind="rss", url="https://a.com/rss", credibility=0.5))
    sid2 = db.upsert_source(Source(name="A2", kind="rss", url="https://a.com/rss", credibility=0.9))
    assert sid1 == sid2
    src = db.get_source(sid1)
    assert src.name == "A2" and src.credibility == 0.9  # updated, not duplicated


def test_insert_item_dedupes_url_key(db):
    sid = _source(db)
    entry = FetchedEntry(url="https://example.com/story?utm_source=x",
                         title="T", published_at=NOW)
    id1 = db.insert_item(sid, entry, raw_path="raw/1.html", fetched_at=NOW)
    id2 = db.insert_item(sid, entry, raw_path="raw/2.html", fetched_at=NOW)
    assert id1 is not None and id2 is None  # second insert skipped


def test_story_lifecycle_and_pending(db):
    sid = _source(db)
    i1 = db.insert_item(sid, FetchedEntry("https://e.com/a", "Saudi port expansion", NOW),
                        "raw/a.html", NOW)
    i2 = db.insert_item(sid, FetchedEntry("https://e.com/b", "Port expansion in Saudi Arabia", NOW),
                        "raw/b.html", NOW)
    story_id = db.create_story(title="Saudi port expansion", primary_item_id=i1)
    db.assign_story(i2, story_id)
    assert db.story_source_count(story_id) == 2
    assert len(db.pending_stories()) == 1  # judge_status 'none', not yet ranked

    jo = JudgeOutput(supply_chain_relevance=9, saudi_gcc_relevance=10, market_impact=8,
                      novelty=7, rationale_supply_chain="r", rationale_saudi_gcc="r",
                      rationale_market_impact="r", rationale_novelty="r",
                      suggested_category="ports-shipping", gist="g")
    db.save_judge_score(story_id, tier="api", model="glm-4-flash",
                        prompt_version="judge_v1", output=jo)
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, priority=88.0, band="high", category="ports-shipping")

    queue = db.queue_stories(limit=10)
    assert queue[0].id == story_id and queue[0].priority == 88.0
    assert db.pending_stories() == []
    assert db.latest_judge(story_id).gist == "g"


def test_wipe_derived_preserves_items_and_sources(db):
    sid = _source(db)
    iid = db.insert_item(sid, FetchedEntry("https://e.com/a", "T", NOW), "raw/a.html", NOW)
    story_id = db.create_story(title="T", primary_item_id=iid)
    db.assign_story(iid, story_id)
    db.wipe_derived()
    assert db.pending_stories() == []
    items = db.window_items(days=7)
    assert len(items) == 1 and items[0].story_id is None
    assert db.all_sources() and db.all_sources()[0].name == "Test Feed"


def test_fetch_run_recording(db):
    sid = _source(db)
    run_id = db.start_fetch_run(sid)
    db.finish_fetch_run(run_id, status="ok", items_found=5)
    db.finish_fetch_run(db.start_fetch_run(sid), status="error", items_found=0, error="timeout")
    runs = db.fetch_runs(sid)
    assert [r.status for r in runs] == ["ok", "error"]


def test_mark_source_health_and_disable(db):
    sid = _source(db)
    db.mark_source_health(sid, healthy=False)
    db.set_source_fetched(sid)
    src = db.get_source(sid)
    assert src.healthy is False and src.last_fetch_at is not None
    assert db.all_sources(enabled_only=True) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.db'`.

- [ ] **Step 3: Implement `sparks/models.py`**

```python
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
```

Note: `JudgeOutput` (the pydantic validation model used by `db.save_judge_score`) is defined in Task 7's `sparks/judge/schema.py`. To keep Task 2 self-contained, `save_judge_score(output: "JudgeOutput")` accepts any object with the ten attribute names above (duck-typed); the test above constructs the real pydantic model, so **create Task 7's `sparks/judge/schema.py` `JudgeOutput` only if running Task 2's test before Task 7 exists fails** — instead, the Task 2 test imports it defensively: put this at the top of `tests/test_db.py`:

```python
try:
    from sparks.judge.schema import JudgeOutput
except ModuleNotFoundError:  # Task 7 not implemented yet: minimal duck-typed stand-in
    from types import SimpleNamespace

    def JudgeOutput(**kw):  # noqa: N802
        return SimpleNamespace(**kw)
```

and drop the pydantic import line from the test as written in Step 1 accordingly.

- [ ] **Step 4: Implement `sparks/db.py`**

```python
"""SQLite storage: schema + repository methods. Single writer (local app)."""
from __future__ import annotations

import pathlib
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from sparks.models import (
    FetchedEntry, ItemRecord, JudgeScoreRow, Source, SourceRun, StoryRecord,
)

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('rss', 'html')),
    url TEXT NOT NULL UNIQUE,
    credibility REAL NOT NULL DEFAULT 0.5,
    category_hint TEXT,
    link_pattern TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    healthy INTEGER NOT NULL DEFAULT 1,
    last_fetch_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS stories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    category TEXT,
    priority REAL,
    band TEXT,
    status TEXT NOT NULL DEFAULT 'clustered',
    judge_status TEXT NOT NULL DEFAULT 'none',
    primary_item_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    story_id INTEGER REFERENCES stories(id),
    url TEXT NOT NULL,
    url_key TEXT NOT NULL UNIQUE,
    title TEXT,
    title_key TEXT,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    raw_path TEXT NOT NULL,
    extracted_text TEXT,
    language TEXT,
    word_count INTEGER,
    status TEXT NOT NULL DEFAULT 'new',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_items_story ON items(story_id);
CREATE TABLE IF NOT EXISTS judge_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    tier TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    supply_chain_relevance INTEGER, saudi_gcc_relevance INTEGER,
    market_impact INTEGER, novelty INTEGER,
    rationale_supply_chain TEXT, rationale_saudi_gcc TEXT,
    rationale_market_impact TEXT, rationale_novelty TEXT,
    suggested_category TEXT, gist TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS fetch_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    items_found INTEGER NOT NULL DEFAULT 0,
    error TEXT
);
"""

def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Database:
    def __init__(self, path: pathlib.Path | str):
        self.path = pathlib.Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.conn.close()

    # -- sources ---------------------------------------------------------
    def upsert_source(self, s: Source) -> int:
        row = self.conn.execute("SELECT id FROM sources WHERE url=?", (s.url,)).fetchone()
        if row:
            self.conn.execute(
                """UPDATE sources SET name=?, kind=?, credibility=?, category_hint=?,
                   link_pattern=?, enabled=?, healthy=? WHERE id=?""",
                (s.name, s.kind, s.credibility, s.category_hint, s.link_pattern,
                 int(s.enabled), int(s.healthy), row["id"]))
            self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            """INSERT INTO sources (name, kind, url, credibility, category_hint,
               link_pattern, enabled, healthy) VALUES (?,?,?,?,?,?,?,?)""",
            (s.name, s.kind, s.url, s.credibility, s.category_hint,
             s.link_pattern, int(s.enabled), int(s.healthy)))
        self.conn.commit()
        return cur.lastrowid

    def _row_to_source(self, r: sqlite3.Row) -> Source:
        return Source(id=r["id"], name=r["name"], kind=r["kind"], url=r["url"],
                      credibility=r["credibility"], category_hint=r["category_hint"],
                      link_pattern=r["link_pattern"], enabled=bool(r["enabled"]),
                      healthy=bool(r["healthy"]), last_fetch_at=_parse_dt(r["last_fetch_at"]))

    def get_source(self, source_id: int) -> Source:
        r = self.conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
        return self._row_to_source(r)

    def all_sources(self, enabled_only: bool = True) -> list[Source]:
        q = "SELECT * FROM sources" + (" WHERE enabled=1" if enabled_only else "") + " ORDER BY id"
        return [self._row_to_source(r) for r in self.conn.execute(q).fetchall()]

    def mark_source_health(self, source_id: int, healthy: bool) -> None:
        self.conn.execute("UPDATE sources SET healthy=? WHERE id=?", (int(healthy), source_id))
        self.conn.commit()

    def set_source_fetched(self, source_id: int) -> None:
        self.conn.execute("UPDATE sources SET last_fetch_at=? WHERE id=?",
                          (datetime.now(timezone.utc).isoformat(), source_id))
        self.conn.commit()

    # -- fetch runs --------------------------------------------------------
    def start_fetch_run(self, source_id: int) -> int:
        cur = self.conn.execute(
            "INSERT INTO fetch_runs (source_id, started_at) VALUES (?,?)",
            (source_id, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()
        return cur.lastrowid

    def finish_fetch_run(self, run_id: int, status: str, items_found: int,
                         error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE fetch_runs SET finished_at=?, status=?, items_found=?, error=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), status, items_found, error, run_id))
        self.conn.commit()

    def fetch_runs(self, source_id: int) -> list[Any]:
        rows = self.conn.execute(
            "SELECT * FROM fetch_runs WHERE source_id=? ORDER BY id", (source_id,)).fetchall()
        return rows

    # -- items -------------------------------------------------------------
    def insert_item(self, source_id: int, entry: FetchedEntry, raw_path: str,
                    fetched_at: datetime) -> int | None:
        from sparks.dedupe import normalize_url, title_key  # local import: Task 6
        url_key = normalize_url(entry.url)
        exists = self.conn.execute("SELECT 1 FROM items WHERE url_key=?", (url_key,)).fetchone()
        if exists:
            return None
        cur = self.conn.execute(
            """INSERT INTO items (source_id, url, url_key, title, title_key,
               published_at, fetched_at, raw_path) VALUES (?,?,?,?,?,?,?,?)""",
            (source_id, entry.url, url_key, entry.title, title_key(entry.title),
             _iso(entry.published_at), _iso(fetched_at), raw_path))
        self.conn.commit()
        return cur.lastrowid

    def _row_to_item(self, r: sqlite3.Row) -> ItemRecord:
        return ItemRecord(id=r["id"], source_id=r["source_id"], url=r["url"],
                          url_key=r["url_key"], title=r["title"], title_key=r["title_key"],
                          published_at=_parse_dt(r["published_at"]),
                          fetched_at=_parse_dt(r["fetched_at"]), raw_path=r["raw_path"],
                          extracted_text=r["extracted_text"], language=r["language"],
                          word_count=r["word_count"], status=r["status"],
                          story_id=r["story_id"])

    def window_items(self, days: int = 7, extracted_only: bool = False) -> list[ItemRecord]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        q = ("SELECT * FROM items WHERE fetched_at >= ?"
             + (" AND extracted_text IS NOT NULL" if extracted_only else "")
             + " ORDER BY id")
        return [self._row_to_item(r)
                for r in self.conn.execute(q, (cutoff,)).fetchall()]

    def update_item_extraction(self, item_id: int, text: str, language: str | None,
                               word_count: int) -> None:
        self.conn.execute(
            "UPDATE items SET extracted_text=?, language=?, word_count=? WHERE id=?",
            (text, language, word_count, item_id))
        self.conn.commit()

    def update_item_status(self, item_id: int, status: str) -> None:
        self.conn.execute("UPDATE items SET status=? WHERE id=?", (status, item_id))
        self.conn.commit()

    # -- stories -----------------------------------------------------------
    def create_story(self, title: str, primary_item_id: int) -> int:
        cur = self.conn.execute("INSERT INTO stories (title, primary_item_id) VALUES (?,?)",
                                (title, primary_item_id))
        story_id = cur.lastrowid
        self.conn.execute("UPDATE items SET story_id=?, status='clustered' WHERE id=?",
                          (story_id, primary_item_id))
        self.conn.commit()
        return story_id

    def assign_story(self, item_id: int, story_id: int) -> None:
        self.conn.execute("UPDATE items SET story_id=?, status='clustered' WHERE id=?",
                          (story_id, item_id))
        self.conn.commit()

    def story_members(self, story_id: int) -> list[ItemRecord]:
        rows = self.conn.execute("SELECT * FROM items WHERE story_id=? ORDER BY id",
                                 (story_id,)).fetchall()
        return [self._row_to_item(r) for r in rows]

    def story_source_count(self, story_id: int) -> int:
        row = self.conn.execute("SELECT COUNT(*) c FROM items WHERE story_id=?",
                                (story_id,)).fetchone()
        return row["c"]

    def story_max_credibility(self, story_id: int) -> float:
        row = self.conn.execute(
            """SELECT MAX(s.credibility) m FROM items i
               JOIN sources s ON s.id = i.source_id WHERE i.story_id=?""",
            (story_id,)).fetchone()
        return row["m"] or 0.0

    def _row_to_story(self, r: sqlite3.Row) -> StoryRecord:
        n = self.story_source_count(r["id"])
        return StoryRecord(id=r["id"], title=r["title"], primary_item_id=r["primary_item_id"],
                           category=r["category"], priority=r["priority"], band=r["band"],
                           status=r["status"], judge_status=r["judge_status"], n_sources=n,
                           created_at=_parse_dt(r["created_at"]))

    def pending_stories(self, limit: int | None = None) -> list[StoryRecord]:
        q = ("SELECT * FROM stories WHERE judge_status='none' AND status='clustered' ORDER BY id"
             + (f" LIMIT {limit}" if limit else ""))
        return [self._row_to_story(r) for r in self.conn.execute(q).fetchall()]

    def queue_stories(self, limit: int = 50, band: str | None = None) -> list[StoryRecord]:
        q = ("SELECT * FROM stories WHERE status='ranked'"
             + (" AND band=?" if band else "")
             + " ORDER BY priority DESC" + f" LIMIT {limit}")
        params = (band,) if band else ()
        return [self._row_to_story(r) for r in self.conn.execute(q, params).fetchall()]

    def set_story_judge_status(self, story_id: int, judge_status: str) -> None:
        self.conn.execute("UPDATE stories SET judge_status=?, updated_at=? WHERE id=?",
                          (judge_status, datetime.now(timezone.utc).isoformat(), story_id))
        self.conn.commit()

    def set_story_ranking(self, story_id: int, priority: float, band: str, category: str) -> None:
        self.conn.execute(
            "UPDATE stories SET priority=?, band=?, category=?, status='ranked', updated_at=? WHERE id=?",
            (priority, band, category, datetime.now(timezone.utc).isoformat(), story_id))
        self.conn.commit()

    # -- judge scores --------------------------------------------------------
    def save_judge_score(self, story_id: int, tier: str, model: str, prompt_version: str,
                         output: Any) -> None:
        self.conn.execute(
            """INSERT INTO judge_scores (story_id, tier, model, prompt_version,
               supply_chain_relevance, saudi_gcc_relevance, market_impact, novelty,
               rationale_supply_chain, rationale_saudi_gcc, rationale_market_impact,
               rationale_novelty, suggested_category, gist)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (story_id, tier, model, prompt_version,
             output.supply_chain_relevance, output.saudi_gcc_relevance,
             output.market_impact, output.novelty,
             output.rationale_supply_chain, output.rationale_saudi_gcc,
             output.rationale_market_impact, output.rationale_novelty,
             output.suggested_category, output.gist))
        self.conn.commit()

    def latest_judge(self, story_id: int) -> JudgeScoreRow | None:
        r = self.conn.execute("SELECT * FROM judge_scores WHERE story_id=? ORDER BY id DESC LIMIT 1",
                              (story_id,)).fetchone()
        if not r:
            return None
        return JudgeScoreRow(story_id=r["story_id"], tier=r["tier"], model=r["model"],
                             prompt_version=r["prompt_version"],
                             supply_chain_relevance=r["supply_chain_relevance"],
                             saudi_gcc_relevance=r["saudi_gcc_relevance"],
                             market_impact=r["market_impact"], novelty=r["novelty"],
                             rationale_supply_chain=r["rationale_supply_chain"],
                             rationale_saudi_gcc=r["rationale_saudi_gcc"],
                             rationale_market_impact=r["rationale_market_impact"],
                             rationale_novelty=r["rationale_novelty"],
                             suggested_category=r["suggested_category"], gist=r["gist"],
                             created_at=_parse_dt(r["created_at"]))

    def all_judge_scores(self) -> list[JudgeScoreRow]:
        rows = self.conn.execute("SELECT * FROM judge_scores").fetchall()
        return [self._row_to_judge(r) for r in rows]

    def _row_to_judge(self, r: sqlite3.Row) -> JudgeScoreRow:
        return JudgeScoreRow(story_id=r["story_id"], tier=r["tier"], model=r["model"],
                             prompt_version=r["prompt_version"],
                             supply_chain_relevance=r["supply_chain_relevance"],
                             saudi_gcc_relevance=r["saudi_gcc_relevance"],
                             market_impact=r["market_impact"], novelty=r["novelty"],
                             rationale_supply_chain=r["rationale_supply_chain"],
                             rationale_saudi_gcc=r["rationale_saudi_gcc"],
                             rationale_market_impact=r["rationale_market_impact"],
                             rationale_novelty=r["rationale_novelty"],
                             suggested_category=r["suggested_category"], gist=r["gist"],
                             created_at=_parse_dt(r["created_at"]))

    # -- replay ---------------------------------------------------------------
    def wipe_derived(self) -> None:
        """Delete derived state; keep sources, fetch_runs, items and raw references."""
        self.conn.executescript(
            "DELETE FROM judge_scores; DELETE FROM stories;"
            "UPDATE items SET story_id=NULL, extracted_text=NULL, language=NULL,"
            " word_count=NULL, status='new';")
        self.conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_db.py -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/models.py sparks/db.py tests/test_db.py
git commit -m "feat: models and sqlite storage layer"
```

---

### Task 3: RSS parsing

**Files:**
- Create: `sparks/fetch/__init__.py` (empty), `sparks/fetch/rss.py`, `tests/fixtures/rss_basic.xml`, `tests/fixtures/rss_google_news.xml`
- Test: `tests/test_fetch_rss.py`

**Interfaces:**
- Consumes: `FetchedEntry` (Task 2).
- Produces: `parse_feed(data: bytes | str, max_items: int = 50) -> list[FetchedEntry]`, `google_news_query_url(query: str, language: str = "en") -> str`.

- [ ] **Step 1: Create fixture files**

`tests/fixtures/rss_basic.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Example Logistics News</title>
  <link>https://example.com</link>
  <item>
    <title>Saudi Ports Authority announces new container terminal at Jeddah</title>
    <link>https://example.com/jeddah-terminal?utm_source=rss</link>
    <pubDate>Tue, 08 Sep 2026 06:30:00 GMT</pubDate>
  </item>
  <item>
    <title>Dammam warehouse district sees record occupancy</title>
    <link>https://example.com/dammam-warehouses</link>
    <pubDate>Mon, 07 Sep 2026 18:00:00 GMT</pubDate>
  </item>
  <item>
    <title>No date on this item</title>
    <link>https://example.com/no-date</link>
  </item>
</channel></rss>
```

`tests/fixtures/rss_google_news.xml` — same structure, one item titled `Maersk opens new Red Sea route - Gulf News` linking to `https://news.google.com/rss/articles/CBMiA?oc=5`.

- [ ] **Step 2: Write the failing tests**

`tests/test_fetch_rss.py`:

```python
from datetime import timezone
from pathlib import Path

from sparks.fetch.rss import google_news_query_url, parse_feed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_feed_basic():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes())
    assert len(entries) == 3
    first = entries[0]
    assert first.title.startswith("Saudi Ports Authority")
    assert first.url == "https://example.com/jeddah-terminal?utm_source=rss"
    assert first.published_at is not None
    assert first.published_at.tzinfo == timezone.utc


def test_parse_feed_missing_date_is_none():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes())
    assert entries[2].published_at is None


def test_parse_feed_caps_items():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes(), max_items=2)
    assert len(entries) == 2


def test_parse_feed_google_news_shape():
    entries = parse_feed((FIXTURES / "rss_google_news.xml").read_bytes())
    assert entries[0].title.startswith("Maersk")
    assert "news.google.com" in entries[0].url


def test_google_news_query_url():
    url = google_news_query_url('"Saudi" "logistics"')
    assert url == ("https://news.google.com/rss/search?q=%22Saudi%22+%22logistics%22"
                   "&hl=en-US&gl=US&ceid=US:en")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_rss.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.fetch'`.

- [ ] **Step 4: Implement `sparks/fetch/rss.py`**

```python
"""RSS/Atom parsing via feedparser."""
from __future__ import annotations

from datetime import timezone
from urllib.parse import quote_plus

import feedparser

from sparks.models import FetchedEntry


def parse_feed(data: bytes | str, max_items: int = 50) -> list[FetchedEntry]:
    parsed = feedparser.parse(data)
    entries: list[FetchedEntry] = []
    for e in parsed.entries[:max_items]:
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            st = getattr(e, attr, None)
            if st:
                published = _from_struct(st)
                break
        entries.append(FetchedEntry(url=e.get("link", ""), title=e.get("title", ""),
                                    published_at=published))
    return entries


def _from_struct(st) -> "object":
    from datetime import datetime
    return datetime(*st[:6], tzinfo=timezone.utc)


def google_news_query_url(query: str, language: str = "en") -> str:
    q = quote_plus(query)
    locale = {"en": ("en-US", "US:en")}.get(language, ("en-US", "US:en"))
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={locale[0]}&gl=US&ceid={locale[1]}")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_rss.py -v`
Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/fetch/ tests/fixtures/rss_basic.xml tests/fixtures/rss_google_news.xml tests/test_fetch_rss.py
git commit -m "feat: rss feed parsing"
```

---

### Task 4: HTML listing parse + politeness + FetchRunner

**Files:**
- Create: `sparks/fetch/html.py`, `sparks/fetch/runner.py`, `tests/fixtures/html_listing.html`
- Test: `tests/test_fetch_html.py`, `tests/test_fetch_runner.py`

**Interfaces:**
- Consumes: `Settings`, `Database` (Tasks 1–2), `parse_feed` (Task 3), `FetchedEntry`, `SourceRun`.
- Produces: `parse_listing(html_text, base_url, link_pattern, max_items=50) -> list[FetchedEntry]`; `FetchRunner(settings, db, client=None).run(sources=None) -> list[SourceRun]`; module function `delay_needed(now: float, last_request: float, delay_s: float) -> float` (pure, for tests).

- [ ] **Step 1: Create fixture file**

`tests/fixtures/html_listing.html`:

```html
<!doctype html><html><body>
<nav><a href="/">Home</a> <a href="/about">About</a></nav>
<main>
  <a href="/press-releases/2026/mawani-new-berth">Mawani inaugurates new berth at Jeddah</a>
  <a href="/press-releases/2026/mawani-record-throughput">Record container throughput Q2</a>
  <a href="/news/2026/some-other-page">Unrelated page</a>
  <a href="https://cdn.example.com/press-releases/2026/pdf-brochure">PDF brochure</a>
</main>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_fetch_html.py`:

```python
from pathlib import Path

from sparks.fetch.html import parse_listing

HTML = (Path(__file__).parent / "fixtures" / "html_listing.html").read_text(encoding="utf-8")


def test_parse_listing_filters_by_pattern_and_resolves_relative():
    entries = parse_listing(HTML, base_url="https://mawani.example/en/media",
                            link_pattern="press-releases")
    urls = [e.url for e in entries]
    assert "https://mawani.example/press-releases/2026/mawani-new-berth" in urls
    assert "https://mawani.example/press-releases/2026/mawani-record-throughput" in urls
    assert all("/news/" not in u for u in urls)
    assert all(u.startswith("http") for u in urls)
    assert entries[0].title == "Mawani inaugurates new berth at Jeddah"


def test_parse_listing_no_pattern_returns_all_http_links():
    entries = parse_listing(HTML, base_url="https://mawani.example", link_pattern=None)
    assert len(entries) >= 4


def test_parse_listing_caps_items():
    entries = parse_listing(HTML, base_url="https://mawani.example", link_pattern=None,
                            max_items=2)
    assert len(entries) == 2
```

`tests/test_fetch_runner.py`:

```python
from pathlib import Path

import httpx
import pytest
import respx

from sparks.db import Database
from sparks.fetch.runner import FetchRunner, delay_needed
from sparks.models import Source

FIXTURES = Path(__file__).parent / "fixtures"
RSS = (FIXTURES / "rss_basic.xml").read_bytes()


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def test_delay_needed_pure():
    assert delay_needed(now=100.0, last_request=100.0, delay_s=3.0) == 3.0
    assert delay_needed(now=103.0, last_request=100.0, delay_s=3.0) == 0.0
    assert delay_needed(now=101.5, last_request=100.0, delay_s=3.0) == pytest.approx(1.5)


@respx.mock
def test_runner_fetches_rss_saves_raw_and_records_run(db, settings, monkeypatch):
    # freeze politeness clock so no real sleeping happens in tests
    monkeypatch.setattr("sparks.fetch.runner.time.sleep", lambda s: None)
    respx.get("https://feed.example/rss").respond(200, content=RSS)
    db.upsert_source(Source(name="Ex", kind="rss", url="https://feed.example/rss",
                            credibility=0.5))
    runner = FetchRunner(settings, db)
    runs = runner.run()
    assert runs[0].status == "ok" and runs[0].items_found == 3 and runs[0].items_new == 3
    items = db.window_items(days=7)
    assert len(items) == 3
    raw_file = Path(items[0].raw_path)
    assert raw_file.exists() and raw_file.read_bytes() == RSS
    assert db.fetch_runs(items[0].source_id)[0].status == "ok"


@respx.mock
def test_runner_repeats_run_inserts_nothing_new(db, settings, monkeypatch):
    monkeypatch.setattr("sparks.fetch.runner.time.sleep", lambda s: None)
    respx.get("https://feed.example/rss").respond(200, content=RSS)
    db.upsert_source(Source(name="Ex", kind="rss", url="https://feed.example/rss"))
    runner = FetchRunner(settings, db)
    runner.run()
    runs = runner.run()
    assert runs[0].items_new == 0 and runs[0].items_found == 3  # url_key dedupe


@respx.mock
def test_runner_source_error_is_isolated(db, settings, monkeypatch):
    monkeypatch.setattr("sparks.fetch.runner.time.sleep", lambda s: None)
    respx.get("https://feed.example/rss").respond(200, content=RSS)
    respx.get("https://bad.example/rss").respond(500)
    db.upsert_source(Source(name="Good", kind="rss", url="https://feed.example/rss"))
    db.upsert_source(Source(name="Bad", kind="rss", url="https://bad.example/rss"))
    runs = FetchRunner(settings, db).run()
    by_name = {r.source_name: r for r in runs}
    assert by_name["Good"].status == "ok"
    assert by_name["Bad"].status == "error" and "500" in by_name["Bad"].error
    assert len(db.window_items(days=7)) == 3  # good source persisted


@respx.mock
def test_runner_respects_robots_disallow(db, settings, monkeypatch):
    monkeypatch.setattr("sparks.fetch.runner.time.sleep", lambda s: None)
    respx.get("https://feed.example/robots.txt").respond(
        200, text="User-agent: *\nDisallow: /")
    db.upsert_source(Source(name="Ex", kind="rss", url="https://feed.example/rss"))
    runs = FetchRunner(settings, db).run()
    assert runs[0].status == "skipped_robots"
    assert runs[0].items_found == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_fetch_html.py tests/test_fetch_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.fetch.html'`.

- [ ] **Step 4: Implement `sparks/fetch/html.py`**

```python
"""Extract candidate article links from HTML listing pages (plumbing only)."""
from __future__ import annotations

import html as html_mod
import re
from urllib.parse import urljoin

from sparks.models import FetchedEntry

_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_listing(html_text: str, base_url: str, link_pattern: str | None,
                  max_items: int = 50) -> list[FetchedEntry]:
    entries: list[FetchedEntry] = []
    seen: set[str] = set()
    for href, inner in _ANCHOR_RE.findall(html_text):
        absolute = urljoin(base_url, href.strip())
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        if link_pattern and not re.search(link_pattern, absolute):
            continue
        title = html_mod.unescape(_TAG_RE.sub("", inner)).strip()
        if not title:
            title = absolute.rsplit("/", 1)[-1].replace("-", " ").strip()
        seen.add(absolute)
        entries.append(FetchedEntry(url=absolute, title=title, published_at=None))
        if len(entries) >= max_items:
            break
    return entries
```

- [ ] **Step 5: Implement `sparks/fetch/runner.py`**

```python
"""FetchRunner: polite, robots-respecting fetching of all sources -> raw files + DB."""
from __future__ import annotations

import hashlib
import pathlib
import re
import time
import urllib.robotparser
from datetime import datetime, timezone

import httpx

from sparks.config import Settings
from sparks.db import Database
from sparks.fetch.html import parse_listing
from sparks.fetch.rss import parse_feed
from sparks.models import FetchedEntry, Source, SourceRun


def delay_needed(now: float, last_request: float, delay_s: float) -> float:
    """Seconds to wait before hitting the same domain again (pure function)."""
    return max(0.0, delay_s - (now - last_request))


def save_raw(raw_dir: pathlib.Path, url: str, content: bytes) -> pathlib.Path:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = hashlib.sha1(f"{url}".encode("utf-8")).hexdigest()[:16]
    day_dir = raw_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{digest}.raw"
    path.write_bytes(content)
    return path


class FetchRunner:
    def __init__(self, settings: Settings, db: Database, client: httpx.Client | None = None):
        self.settings = settings
        self.db = db
        self._client = client
        self._domain_last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.settings.fetch.user_agent,
                         "Accept-Language": "en, ar;q=0.8"},
                timeout=self.settings.fetch.timeout_seconds,
                follow_redirects=True)
        return self._client

    def _polite_wait(self, domain: str) -> None:
        now = time.monotonic()
        wait = delay_needed(now, self._domain_last.get(domain, 0.0),
                            self.settings.fetch.per_domain_delay_seconds)
        if wait > 0:
            time.sleep(wait)
        self._domain_last[domain] = time.monotonic()

    def _robots_allows(self, url: str) -> bool:
        rp = self._robots_cache(url)
        return rp is None or rp.can_fetch(self.settings.fetch.user_agent, url)

    def _robots_cache(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        from urllib.parse import urlsplit
        parts = urlsplit(url)
        host = f"{parts.scheme}://{parts.netloc}"
        if host not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                resp = self.client.get(host + "/robots.txt")  # goes through httpx -> mockable
                resp.raise_for_status()
                rp.parse(resp.text.splitlines())
                self._robots[host] = rp
            except Exception:
                self._robots[host] = None  # unreachable robots -> allow
        return self._robots[host]

    def _fetch_bytes(self, url: str) -> bytes:
        self._polite_wait(url.split("/")[2] if "://" in url else url)
        response = self.client.get(url)
        response.raise_for_status()
        return response.content

    def run(self, sources: list[Source] | None = None) -> list[SourceRun]:
        sources = sources if sources is not None else self.db.all_sources(enabled_only=True)
        runs: list[SourceRun] = []
        for source in sources:
            run = SourceRun(source_id=source.id or -1, source_name=source.name, status="ok")
            run_id = self.db.start_fetch_run(source.id or -1)
            try:
                if not self._robots_allows(source.url):
                    run.status = "skipped_robots"
                    self.db.finish_fetch_run(run_id, "skipped_robots", 0)
                    runs.append(run)
                    continue
                content = self._fetch_bytes(source.url)
                if source.kind == "rss":
                    entries = parse_feed(content, self.settings.fetch.max_items_per_source)
                else:
                    html_text = content.decode("utf-8", errors="replace")
                    pattern = source.link_pattern or re.escape(
                        source.url.rsplit("/", 1)[-1])  # default: match last path segment
                    entries = parse_listing(html_text, source.url, pattern,
                                            self.settings.fetch.max_items_per_source)
                run.items_found = len(entries)
                for entry in entries:
                    if not entry.url:
                        continue
                    raw_path = save_raw(self.settings.raw_dir, entry.url, content)
                    new_id = self.db.insert_item(
                        source.id or -1, entry, raw_path=str(raw_path),
                        fetched_at=datetime.now(timezone.utc))
                    if new_id is not None:
                        run.items_new += 1
                self.db.mark_source_health(source.id or -1, healthy=True)
            except Exception as exc:  # per-source isolation (spec 11)
                run.status = "error"
                run.error = f"{type(exc).__name__}: {exc}"
                self.db.finish_fetch_run(run_id, "error", run.items_found, run.error)
                self.db.mark_source_health(source.id or -1, healthy=False)
            else:
                self.db.finish_fetch_run(run_id, "ok", run.items_found)
                self.db.set_source_fetched(source.id or -1)
            runs.append(run)
        return runs
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_fetch_html.py tests/test_fetch_runner.py -v`
Expected: 3 + 5 = 8 PASSED.

- [ ] **Step 7: Commit**

```bash
git add sparks/fetch/html.py sparks/fetch/runner.py tests/fixtures/html_listing.html tests/test_fetch_html.py tests/test_fetch_runner.py
git commit -m "feat: html listing parser and polite fetch runner"
```

---

### Task 5: Article extraction + noise filter

**Files:**
- Create: `sparks/extract.py`, `tests/fixtures/article_good.html`, `tests/fixtures/article_short.html`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: nothing new (operates on raw HTML strings).
- Produces: `ExtractedText(text: str, word_count: int, language: str | None)` and `extract_article(html_text: str) -> ExtractedText | None` — `None` means "not a real article" (<150 words).

- [ ] **Step 1: Create fixture files**

`tests/fixtures/article_good.html` — a realistic article page whose *body* has ≥200 words about Jeddah port expansion (write any 200+ word business prose between `<article>` tags; include nav/boilerplate around it):

```html
<!doctype html><html><head><title>Jeddah terminal expansion - Example News</title></head>
<body>
<nav><a href="/">Home</a><a href="/business">Business</a></nav>
<article><h1>Jeddah Islamic Port to add two million TEU capacity</h1>
<p>Saudi Ports Authority (Mawani) said on Tuesday it will expand container handling
capacity at Jeddah Islamic Port by two million twenty-foot equivalent units as part
of a broader program to position the kingdom as a logistics gateway between Asia,
Africa and Europe.</p>
<p>The project includes new ship-to-shore cranes, an extended quay wall and
automated gate systems expected to cut truck turnaround times significantly.
Contracts were awarded to a consortium of international equipment suppliers, with
first phase completion targeted within eighteen months.</p>
<p>Analysts said the expansion supports national logistics zone ambitions under
Vision 2030, where non-oil trade corridors are expected to absorb growing
transshipment demand currently routed through competing regional hubs.</p>
<p>Port throughput at Jeddah has grown at a double digit pace over recent quarters,
driven by Red Sea route realignments and growing imports for giga-project
construction programs in the western region.</p>
<p>Additional investments in rail links between the port and inland dry ports are
under study, officials said, alongside digitalization of customs documentation
aimed at reducing dwell time for bonded cargo moving to Riyadh.</p>
</article>
<footer>Copyright Example News. All rights reserved.</footer>
</body></html>
```

`tests/fixtures/article_short.html`:

```html
<!doctype html><html><body><article><h1>Brief</h1>
<p>Only a few words here.</p></article></body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_extract.py`:

```python
from pathlib import Path

from sparks.extract import extract_article

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_body_and_counts_words():
    result = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8"))
    assert result is not None
    assert result.word_count >= 150
    assert "Jeddah Islamic Port" in result.text
    assert "Home" not in result.text.split("\n")[0]  # nav stripped
    assert "Copyright Example News" not in result.text


def test_short_page_returns_none():
    assert extract_article((FIXTURES / "article_short.html").read_text(encoding="utf-8")) is None


def test_garbage_returns_none():
    assert extract_article("<html><body></body></html>") is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_extract.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.extract'`.

- [ ] **Step 4: Implement `sparks/extract.py`**

```python
"""Article extraction via trafilatura + mechanical noise filter."""
from __future__ import annotations

from dataclasses import dataclass

import trafilatura

MIN_WORDS = 150  # spec 4.2: discard non-articles below this


@dataclass
class ExtractedText:
    text: str
    word_count: int
    language: str | None = None


def extract_article(html_text: str) -> ExtractedText | None:
    text = trafilatura.extract(html_text, include_comments=False,
                               include_tables=True, favor_recall=True)
    if not text:
        return None
    word_count = len(text.split())
    if word_count < MIN_WORDS:
        return None
    return ExtractedText(text=text, word_count=word_count, language=None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_extract.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/extract.py tests/fixtures/article_good.html tests/fixtures/article_short.html tests/test_extract.py
git commit -m "feat: trafilatura extraction with noise filter"
```

---

### Task 6: Deduplication + clustering

**Files:**
- Create: `sparks/dedupe.py`, `tests/fixtures/article_variant.html`
- Test: `tests/test_dedupe.py`

**Interfaces:**
- Consumes: `ItemRecord` (Task 2); used internally by `Database.insert_item` (already wired in Task 2).
- Produces: `normalize_url(url) -> str`, `title_key(title) -> str`, `simhash(text) -> int`, `hamming(a, b) -> int`, `ClusterDecision(primary_item_id, member_item_ids, title)` and `build_clusters(items: list[ItemRecord], window_days: int = 7) -> list[ClusterDecision]`.

- [ ] **Step 1: Create fixture**

`tests/fixtures/article_variant.html` — identical body to `article_good.html` except the headline reads `<h1>Jeddah Islamic Port to add 2 million TEU of capacity</h1>` and one sentence reworded (e.g. "Mawani announced Tuesday" instead of "Mawani said on Tuesday"). This produces a simhash distance ≤ 3 but a title similarity below 90.

- [ ] **Step 2: Write the failing tests**

`tests/test_dedupe.py`:

```python
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sparks.dedupe import (build_clusters, hamming, normalize_url, simhash, title_key)
from sparks.extract import extract_article
from sparks.models import ItemRecord

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


def item(iid, title, text=None, published=NOW, credibility_src=None, url=None):
    return ItemRecord(id=iid, source_id=1, url=url or f"https://x.com/{iid}",
                      url_key=normalize_url(url or f"https://x.com/{iid}"),
                      title=title, title_key=title_key(title), published_at=published,
                      fetched_at=NOW, raw_path="", extracted_text=text)


def test_normalize_url_strips_tracking_and_normalizes():
    assert normalize_url("https://Example.com/story/?utm_source=rss&fbclid=abc&id=2") == \
           normalize_url("https://example.com/story?id=2")
    assert normalize_url("https://example.com/story") == normalize_url("https://example.com/story/")
    assert normalize_url("https://example.com/a?utm_campaign=x") == "https://example.com/a"


def test_title_key_collapses_case_and_punctuation():
    assert title_key("Red-Sea Shipping: Update!") == title_key("red sea shipping update")


def test_simhash_near_identical_texts_are_close():
    a = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8")).text
    b = extract_article((FIXTURES / "article_variant.html").read_text(encoding="utf-8")).text
    assert hamming(simhash(a), simhash(b)) <= 6
    other = "Rainfall disrupted railway timetables across northern Europe yesterday " * 10
    assert hamming(simhash(a), simhash(other)) > 10


def test_build_clusters_merges_same_title_and_similar_body():
    a = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8")).text
    b = extract_article((FIXTURES / "article_variant.html").read_text(encoding="utf-8")).text
    items = [
        item(1, "Saudi Ports Authority announces new container terminal at Jeddah", a),
        item(2, "Saudi Ports Authority announces new container terminal at Jeddah!", b,
             url="https://y.com/2"),   # same title modulo punctuation + near-same body
        item(3, "Dammam warehouse district sees record occupancy", url="https://y.com/3"),
    ]
    clusters = build_clusters(items, window_days=7)
    assert len(clusters) == 2
    merged = max(clusters, key=lambda c: len(c.member_item_ids))
    assert {1, 2} <= set(merged.member_item_ids)
    assert 3 in [m for c in clusters for m in c.member_item_ids]


def test_build_clusters_respects_time_window():
    old = item(1, "Same headline story", published=NOW - timedelta(days=10))
    new = item(2, "Same headline story", published=NOW, url="https://y.com/2")
    clusters = build_clusters([old, new], window_days=7)
    assert len(clusters) == 2  # too far apart to merge


def test_build_clusters_picks_primary_by_recency_then_id():
    items = [item(5, "Headline A", published=NOW - timedelta(hours=2)),
             item(2, "Headline A", published=NOW, url="https://y.com/2")]
    clusters = build_clusters(items)
    assert clusters[0].primary_item_id == 2  # newest becomes primary
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.dedupe'`.

- [ ] **Step 4: Implement `sparks/dedupe.py`**

```python
"""Deduplication and clustering: URL keys, fuzzy titles, simhash bodies, union-find.

This is plumbing (spec: no regex decides *relevance*) — merging near-identical
stories is identity resolution, not editorial judgment.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from sparks.models import ItemRecord

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "igshid")
TITLE_DROP = re.compile(r"[^a-z0-9؀-ۿ]+")
SHINGLE_SIZE = 4
SIMHASH_BITS = 64


def normalize_url(url: str) -> str:
    s = urlsplit(url.strip().lower())
    query = sorted((k, v) for k, v in parse_qsl(s.query)
                   if not any(k.startswith(p) for p in TRACKING_PREFIXES))
    return urlunsplit((s.scheme, s.netloc, s.path.rstrip("/"), urlencode(query), ""))


def title_key(title: str | None) -> str | None:
    if not title:
        return None
    return " ".join(TITLE_DROP.split(title.lower())).strip() or None


def _shingles(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9؀-ۿ]+", text.lower())
    if len(words) <= SHINGLE_SIZE:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + SHINGLE_SIZE]) for i in range(len(words) - SHINGLE_SIZE + 1)}


def simhash(text: str | None) -> int:
    if not text:
        return 0
    votes = [0] * SIMHASH_BITS
    for shingle in _shingles(text):
        digest = hashlib.md5(shingle.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        for b in range(SIMHASH_BITS):
            votes[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(SIMHASH_BITS):
        if votes[b] > 0:
            out |= 1 << b
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass
class ClusterDecision:
    primary_item_id: int
    member_item_ids: list[int] = field(default_factory=list)
    title: str = ""


def build_clusters(items: list[ItemRecord], window_days: int = 7,
                   title_threshold: int = 90, simhash_threshold: int = 3) -> list[ClusterDecision]:
    """Cluster items into stories via union-find. Edges (within time window):
    title token-set ratio >= title_threshold OR body simhash distance <= simhash_threshold."""
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    hashes = [simhash(it.extracted_text) for it in items]
    window = timedelta(days=window_days)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            times = [t for t in (a.published_at or a.fetched_at, b.published_at or b.fetched_at) if t]
            if times and abs(times[0] - times[1]) > window:
                continue
            same_title = (a.title_key and b.title_key
                          and fuzz.token_set_ratio(a.title_key, b.title_key) >= title_threshold)
            close_body = hamming(hashes[i], hashes[j]) <= simhash_threshold
            if same_title or close_body:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(len(items)):
        groups.setdefault(find(idx), []).append(idx)

    clusters: list[ClusterDecision] = []
    for members in groups.values():
        def sort_key(m: int) -> tuple:
            it = items[m]
            t = it.published_at or it.fetched_at
            return (t is not None, t or items[m].fetched_at, -it.id)
        primary = sorted(members, key=sort_key, reverse=True)[0]
        clusters.append(ClusterDecision(
            primary_item_id=items[primary].id,
            member_item_ids=[items[m].id for m in members],
            title=items[primary].title or items[primary].url,
        ))
    return clusters
```

Note: `sort_key` returning `(bool, datetime, int)` with `reverse=True` picks the *newest* item (True sorts above False; newest datetime above older; higher id breaks ties) — matching `test_build_clusters_picks_primary_by_recency_then_id`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_dedupe.py -v`
Expected: 7 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/dedupe.py tests/fixtures/article_variant.html tests/test_dedupe.py
git commit -m "feat: story deduplication and clustering"
```

---

### Task 7: Judge schema + versioned prompt

**Files:**
- Create: `sparks/judge/__init__.py` (empty), `sparks/judge/schema.py`, `sparks/judge/prompt.py`, `sparks/prompts/judge_v1.md`
- Test: `tests/test_judge_schema.py`, `tests/test_judge_prompt.py`

**Interfaces:**
- Consumes: `Settings.prompts_dir` override (Task 1).
- Produces: `CATEGORIES: list[str]`, `PROMPT_VERSION = "judge_v1"`, `JudgeError(Exception)`, `StoryContext(title: str, lead: str, body: str, n_sources: int)`, pydantic `JudgeOutput` with fields `supply_chain_relevance, saudi_gcc_relevance, market_impact, novelty` (ints 0–10), `rationale_supply_chain, rationale_saudi_gcc, rationale_market_impact, rationale_novelty` (str), `suggested_category` (normalized into `CATEGORIES`), `gist` (str); and `render_judge_prompt(ctx: StoryContext) -> list[dict]` returning chat messages `[{"role": "system", ...}, {"role": "user", ...}]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_judge_schema.py`:

```python
import pytest
from pydantic import ValidationError

from sparks.judge.schema import CATEGORIES, JudgeOutput, StoryContext, PROMPT_VERSION


def make_output(**over):
    base = dict(
        supply_chain_relevance=8, saudi_gcc_relevance=9, market_impact=6, novelty=5,
        rationale_supply_chain="core logistics story", rationale_saudi_gcc="KSA port capex",
        rationale_market_impact="large capex", rationale_novelty="follows prior plan",
        suggested_category="ports-shipping", gist="Mawani expands Jeddah capacity.")
    base.update(over)
    return JudgeOutput(**base)


def test_valid_output_and_version():
    jo = make_output()
    assert 0 <= jo.market_impact <= 10
    assert jo.suggested_category in CATEGORIES
    assert PROMPT_VERSION == "judge_v1"


def test_out_of_range_rejected():
    with pytest.raises(ValidationError):
        make_output(market_impact=11)
    with pytest.raises(ValidationError):
        make_output(supply_chain_relevance=-1)


def test_unknown_category_normalized_to_other():
    assert make_output(suggested_category="totally-new-category").suggested_category == "other"


def test_story_context_holds_fields():
    ctx = StoryContext(title="T", lead="L", body="B", n_sources=3)
    assert ctx.n_sources == 3
```

`tests/test_judge_prompt.py`:

```python
from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import StoryContext


def test_prompt_contains_context_and_schema():
    ctx = StoryContext(title="Jeddah expansion", lead="Mawani announced capacity works.",
                       body="Body text here.", n_sources=4)
    messages = render_judge_prompt(ctx)
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "Jeddah expansion" in user and "Body text here." in user
    assert "4" in user
    for field in ("supply_chain_relevance", "rationale_market_impact", "suggested_category"):
        assert field in messages[0]["content"]


def test_prompt_anchor_examples_present():
    messages = render_judge_prompt(StoryContext("t", "l", "b", 1))
    assert "ANCHOR" in messages[0]["content"]


def test_prompt_override_dir_used(settings, tmp_path):
    override = tmp_path / "prompts" / "judge_v1.md"
    override.parent.mkdir(parents=True)
    override.write_text("OVERRIDE SYSTEM {{SCHEMA_FIELDS}}", encoding="utf-8")
    settings.prompts_dir = tmp_path / "prompts"
    from sparks.judge import prompt as prompt_mod
    messages = prompt_mod.render_judge_prompt(
        StoryContext("t", "l", "b", 1), settings=settings)
    assert messages[0]["content"] == "OVERRIDE SYSTEM supply_chain_relevance"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_judge_schema.py tests/test_judge_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.judge'`.

- [ ] **Step 3: Implement `sparks/judge/schema.py`**

```python
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
```

- [ ] **Step 4: Create `sparks/prompts/judge_v1.md`**

```markdown
# Judge Prompt — version judge_v1

## SYSTEM

You are the editorial desk analyst for Supply Chain Sparks, a supply-chain
intelligence publication focused on Saudi Arabia and the GCC. You triage the
morning queue the way a senior editor would: fast, consistent, and judgment-first.

Score these four factors, each an integer 0-10:

- supply_chain_relevance — how central is this story to supply chain management:
  logistics, ports, shipping, warehousing, procurement, manufacturing, transport,
  trade flows? 10 = the story IS supply chain news. 0 = unrelated.
- saudi_gcc_relevance — how much does it affect Saudi Arabia or the GCC
  specifically? 10 = directly about KSA/GCC operations, policy, investment or
  companies. Global stories with a stated regional impact score 5-7. Purely
  domestic news about other regions scores 0-2.
- market_impact — how much would this change decisions for practitioners in the
  region? Capacity changes, major contracts, policy shifts, disruptions score
  high; routine announcements and commentary score low.
- novelty — is this genuinely new information, or a re-report/continuation of
  something already known? First reports score high.

ANCHOR — score 9 example: "Saudi Ports Authority awards $2bn contract for new
Jeddah container terminal, adding 2m TEU capacity" (direct KSA supply chain
infrastructure, large capex, first report).

ANCHOR — score 3 example: "Global container rates dipped 2% this week" (relevant
industry, but global, incremental, no regional specificity).

ANCHOR — score 1 example: "Retail chain launches summer fashion collection"
(no supply chain relevance).

Write a one-line rationale for each factor (editor's-note style, cite the
concrete fact that drove your score). Write a 2-sentence factual gist of the
story. Choose suggested_category from exactly: {{SCHEMA_CATEGORIES}}.

Return ONLY a JSON object with exactly these keys:
{{SCHEMA_FIELDS}}

## USER

Title: {{TITLE}}

Lead: {{LEAD}}

Body (may be truncated):
{{BODY}}

Independent sources reporting this story: {{N_SOURCES}}
```

- [ ] **Step 5: Implement `sparks/judge/prompt.py`**

```python
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
```

(The `test_prompt_contains_context_and_schema` assertion that field names appear in the system message holds because `{{SCHEMA_FIELDS}}` is substituted there; the same is true of `{{SCHEMA_CATEGORIES}}`.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_judge_schema.py tests/test_judge_prompt.py -v`
Expected: 4 + 3 = 7 PASSED.

- [ ] **Step 7: Commit**

```bash
git add sparks/judge/ sparks/prompts/ tests/test_judge_schema.py tests/test_judge_prompt.py
git commit -m "feat: judge output schema and versioned rubric prompt"
```

---

### Task 8: Judge clients — API tier + Ollama local tier

**Files:**
- Create: `sparks/judge/api.py`, `sparks/judge/local.py`
- Test: `tests/test_judge_clients.py`

**Interfaces:**
- Consumes: `render_judge_prompt` (Task 7), `JudgeOutput`, `JudgeError`, `StoryContext`, `Settings.judge` configs.
- Produces: `ApiJudge(cfg: ApiJudgeConfig, client: httpx.Client | None = None)` and `OllamaJudge(cfg: LocalJudgeConfig, client: httpx.Client | None = None)`, each with `.judge(ctx: StoryContext, settings: Settings | None = None) -> JudgeOutput`, raising `JudgeError` on transport failure or invalid output after one retry. Both accept an optional `settings` argument passed through to `render_judge_prompt`.

- [ ] **Step 1: Write the failing tests**

`tests/test_judge_clients.py`:

```python
import json

import httpx
import pytest
import respx

from sparks.config import ApiJudgeConfig, LocalJudgeConfig
from sparks.judge.api import ApiJudge
from sparks.judge.local import OllamaJudge
from sparks.judge.schema import JudgeError, StoryContext

CTX = StoryContext(title="Jeddah expansion", lead="Mawani announced works.",
                   body="Body text.", n_sources=2)

VALID = {
    "supply_chain_relevance": 9, "saudi_gcc_relevance": 10, "market_impact": 8,
    "novelty": 7, "rationale_supply_chain": "r", "rationale_saudi_gcc": "r",
    "rationale_market_impact": "r", "rationale_novelty": "r",
    "suggested_category": "ports-shipping", "gist": "Mawani expands Jeddah.",
}


def _chat_response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@respx.mock
def test_api_judge_parses_json_with_code_fences():
    fenced = "```json\n" + json.dumps(VALID) + "\n```"
    route = respx.post("https://api.example/v4/chat/completions").respond(
        200, json={"choices": [{"message": {"content": fenced}}]})
    judge = ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4",
                                    model="m", api_key="k"))
    out = judge.judge(CTX)
    assert out.market_impact == 8
    body = json.loads(route.calls.last.request.content.decode())
    assert body["model"] == "m" and body["messages"][0]["role"] == "system"
    assert route.calls.last.request.headers["authorization"] == "Bearer k"


@respx.mock
def test_api_judge_retries_once_on_invalid_then_succeeds():
    route = respx.post("https://api.example/v4/chat/completions")
    route.side_effect = [
        httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
        httpx.Response(200, json=_chat_response(VALID)),
    ]
    out = ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                  api_key="k")).judge(CTX)
    assert out.supply_chain_relevance == 9 and route.call_count == 2


@respx.mock
def test_api_judge_raises_after_retry_exhausted():
    respx.post("https://api.example/v4/chat/completions").respond(
        200, json={"choices": [{"message": {"content": "still not json"}}]})
    with pytest.raises(JudgeError):
        ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                api_key="k")).judge(CTX)


@respx.mock
def test_api_judge_http_error_raises_judge_error():
    respx.post("https://api.example/v4/chat/completions").respond(401)
    with pytest.raises(JudgeError):
        ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                api_key="bad")).judge(CTX)


@respx.mock
def test_ollama_judge_parses_content():
    respx.post("http://localhost:11434/api/chat").respond(
        200, json={"message": {"content": json.dumps(VALID)}})
    out = OllamaJudge(LocalJudgeConfig()).judge(CTX)
    assert out.suggested_category == "ports-shipping"
    req = json.loads(respx.calls.last.request.content.decode())
    assert req["model"] == "qwen2.5:3b" and req["format"] == "json"


@respx.mock
def test_ollama_judge_connection_error_raises():
    respx.post("http://localhost:11434/api/chat").mock(side_effect=httpx.ConnectError("no"))
    with pytest.raises(JudgeError):
        OllamaJudge(LocalJudgeConfig()).judge(CTX)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_judge_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.judge.api'`.

- [ ] **Step 3: Implement `sparks/judge/api.py`**

```python
"""API judge tier: any OpenAI-compatible /chat/completions endpoint."""
from __future__ import annotations

import json
import re

import httpx

from sparks.config import Settings, ApiJudgeConfig
from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


def _parse_content(content: str) -> JudgeOutput:
    text = content.strip()
    text = _FENCE_RE.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise JudgeError(f"no JSON object in judge reply: {content[:120]!r}")
    try:
        return JudgeOutput.model_validate(json.loads(text[start:end + 1]))
    except Exception as exc:
        raise JudgeError(f"invalid judge payload: {exc}") from exc


class ApiJudge:
    def __init__(self, cfg: ApiJudgeConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=60)
        return self._client

    def judge(self, ctx: StoryContext, settings: Settings | None = None) -> JudgeOutput:
        messages = render_judge_prompt(ctx, settings=settings)
        payload = {"model": self.cfg.model, "messages": messages,
                   "temperature": 0.2, "response_format": {"type": "json_object"}}
        headers = {"authorization": f"Bearer {self.cfg.api_key}"}
        last_error: Exception | None = None
        for _ in range(2):  # one retry on invalid output (spec 11)
            try:
                resp = self.client.post(f"{self.cfg.base_url.rstrip('/')}/chat/completions",
                                        json=payload, headers=headers)
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                return _parse_content(content)
            except JudgeError as exc:
                last_error = exc
            except Exception as exc:
                raise JudgeError(f"api judge request failed: {exc}") from exc
        raise JudgeError(f"api judge invalid output after retry: {last_error}")
```

- [ ] **Step 4: Implement `sparks/judge/local.py`**

```python
"""Local judge tier: Ollama /api/chat on localhost."""
from __future__ import annotations

import json

import httpx

from sparks.config import LocalJudgeConfig, Settings
from sparks.judge.api import _parse_content
from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext


class OllamaJudge:
    def __init__(self, cfg: LocalJudgeConfig, client: httpx.Client | None = None):
        self.cfg = cfg
        self._client = client

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=300)  # CPU inference is slow
        return self._client

    def judge(self, ctx: StoryContext, settings: Settings | None = None) -> JudgeOutput:
        messages = render_judge_prompt(ctx, settings=settings)
        payload = {"model": self.cfg.model, "messages": messages, "format": "json",
                   "stream": False, "options": {"temperature": 0.2}}
        last_error: Exception | None = None
        for _ in range(2):
            try:
                resp = self.client.post(f"{self.cfg.ollama_url.rstrip('/')}/api/chat",
                                        json=payload)
                resp.raise_for_status()
                content = resp.json()["message"]["content"]
                return _parse_content(content)
            except JudgeError as exc:
                last_error = exc
            except Exception as exc:
                raise JudgeError(f"ollama judge request failed: {exc}") from exc
        raise JudgeError(f"ollama judge invalid output after retry: {last_error}")
```

Note: `ApiJudge` and `OllamaJudge` have identical `.judge(ctx, settings=None)` signatures — the service (Task 9) treats them interchangeably. If the configured endpoint rejects `response_format`, remove that key from the payload (GLM and OpenAI accept it; keep a code comment saying so).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_judge_clients.py -v`
Expected: 6 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/judge/api.py sparks/judge/local.py tests/test_judge_clients.py
git commit -m "feat: api and ollama judge clients"
```

---

### Task 9: Judge service — tiering, fallback, unscored marking

**Files:**
- Create: `sparks/judge/service.py`
- Test: `tests/test_judge_service.py`

**Interfaces:**
- Consumes: `Settings`, `Database` (Tasks 1–2), `ApiJudge`/`OllamaJudge` (Task 8), `StoryContext`, `JudgeOutput`, `JudgeError`, `PROMPT_VERSION`.
- Produces: `JudgeService(settings, db, api_judge=None, local_judge=None)` with `.judge_story(story_id: int) -> str` (returns `"api"`, `"local"`, or `"unscored"`) and `.judge_pending(limit: int | None = None) -> tuple[int, int]` (`(judged, unscored)`). Context assembly rule: title = primary item title; lead = first 2 sentences of extracted text (or first 400 chars); body = remainder capped at 1,500 chars by the prompt renderer.

- [ ] **Step 1: Write the failing tests**

`tests/test_judge_service.py`:

```python
import pytest

from sparks.db import Database
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext
from sparks.judge.service import JudgeService
from sparks.models import FetchedEntry, Source

VALID = JudgeOutput(supply_chain_relevance=9, saudi_gcc_relevance=10, market_impact=8,
                    novelty=7, rationale_supply_chain="r", rationale_saudi_gcc="r",
                    rationale_market_impact="r", rationale_novelty="r",
                    suggested_category="ports-shipping", gist="g")


class FakeJudge:
    def __init__(self, raise_=None):
        self.raise_ = raise_
        self.calls = []

    def judge(self, ctx, settings=None):
        self.calls.append(ctx)
        if self.raise_:
            raise self.raise_
        return VALID


def _story(db):
    from datetime import datetime, timezone
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    sid = db.upsert_source(Source(name="S", kind="rss", url="https://s.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://s.com/a", "Jeddah expansion", now),
                         "raw/a.html", now)
    db.update_item_extraction(iid, text="First sentence here. Second sentence. " + "word " * 200,
                              language=None, word_count=205)
    return db.create_story(title="Jeddah expansion", primary_item_id=iid)


def test_api_tier_success(db, settings):
    story_id = _story(db)
    api = FakeJudge()
    tier = JudgeService(settings, db, api_judge=api, local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "api"
    assert api.calls[0].title == "Jeddah expansion"
    assert api.calls[0].lead.startswith("First sentence here.")
    assert db.latest_judge(story_id).tier == "api"


def test_fallback_to_local_when_api_fails(db, settings):
    settings.judge.default_tier = "api"
    story_id = _story(db)
    local = FakeJudge()
    tier = JudgeService(settings, db, api_judge=FakeJudge(raise_=JudgeError("boom")),
                        local_judge=local).judge_story(story_id)
    assert tier == "local" and len(local.calls) == 1


def test_local_disabled_and_api_fails_marks_unscored(db, settings):
    settings.judge.default_tier = "api"
    settings.judge.local.enabled = False
    story_id = _story(db)
    tier = JudgeService(settings, db, api_judge=FakeJudge(raise_=JudgeError("boom")),
                        local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "unscored"
    assert db.pending_stories() == []  # no longer pending: marked
    story = [s for s in db.queue_stories(50)][0:1]
    assert db.latest_judge(story_id) is None


def test_local_tier_used_when_default(db, settings):
    settings.judge.default_tier = "local"
    story_id = _story(db)
    api = FakeJudge()
    tier = JudgeService(settings, db, api_judge=api,
                        local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "local" and api.calls == []


def test_judge_pending_counts(db, settings):
    _story(db)
    judged, unscored = JudgeService(settings, db, api_judge=FakeJudge(),
                                    local_judge=FakeJudge()).judge_pending()
    assert (judged, unscored) == (1, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_judge_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.judge.service'`.

- [ ] **Step 3: Implement `sparks/judge/service.py`**

```python
"""JudgeService: tier selection, api->local fallback, unscored marking."""
from __future__ import annotations

import re

from sparks.config import Settings
from sparks.db import Database
from sparks.judge.api import ApiJudge
from sparks.judge.local import OllamaJudge
from sparks.judge.schema import PROMPT_VERSION, JudgeError, StoryContext

_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


class JudgeService:
    def __init__(self, settings: Settings, db: Database,
                 api_judge: ApiJudge | None = None,
                 local_judge: OllamaJudge | None = None):
        self.settings = settings
        self.db = db
        self.api_judge = api_judge or ApiJudge(settings.judge.api)
        self.local_judge = local_judge or OllamaJudge(settings.judge.local)

    def _context_for(self, story) -> StoryContext:
        members = self.db.story_members(story.id)
        primary = next((m for m in members if m.id == story.primary_item_id), members[0])
        text = (primary.extracted_text or "").strip()
        sentences = _SENTENCE_RE.split(text)
        lead = " ".join(sentences[:2])[:400]
        body = text[len(lead):].strip() if len(text) > len(lead) else text
        return StoryContext(title=primary.title or story.title, lead=lead, body=body,
                            n_sources=max(1, len(members)))

    def _tier_order(self) -> list[tuple[str, object]]:
        order = []
        default, other = "api", "local"
        if self.settings.judge.default_tier == "local":
            default, other = "local", "api"
        order.append((default, getattr(self, f"{default}_judge")))
        if self.settings.judge.local.enabled:
            order.append((other, getattr(self, f"{other}_judge")))
        seen: set[str] = set()
        unique = []
        for tier, judge in order:
            if tier not in seen and judge is not None:
                unique.append((tier, judge))
                seen.add(tier)
        return unique

    def judge_story(self, story_id: int) -> str:
        pending = [s for s in self.db.pending_stories() if s.id == story_id]
        if not pending:
            story_row = self.db.queue_stories(10_000)
            pending = [s for s in story_row if s.id == story_id]
        if not pending:
            return "unscored"
        ctx = self._context_for(pending[0])
        for tier, judge in self._tier_order():
            try:
                output = judge.judge(ctx, settings=self.settings)
            except JudgeError:
                continue
            self.db.save_judge_score(story_id, tier=tier, model=self._model_for(tier),
                                     prompt_version=PROMPT_VERSION, output=output)
            self.db.set_story_judge_status(story_id, tier)
            return tier
        self.db.set_story_judge_status(story_id, "unscored")
        return "unscored"

    def _model_for(self, tier: str) -> str:
        if tier == "api":
            return self.settings.judge.api.model
        return self.settings.judge.local.model

    def judge_pending(self, limit: int | None = None) -> tuple[int, int]:
        judged = unscored = 0
        for story in self.db.pending_stories(limit=limit):
            result = self.judge_story(story.id)
            if result == "unscored":
                unscored += 1
            else:
                judged += 1
        return judged, unscored
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_judge_service.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/judge/service.py tests/test_judge_service.py
git commit -m "feat: judge service with tier fallback"
```

---

### Task 10: Composite ranker

**Files:**
- Create: `sparks/rank.py`
- Test: `tests/test_rank.py`

**Interfaces:**
- Consumes: `RankConfig` (Task 1), judge scores (ints), source credibility, corroboration count, story age.
- Produces: `compute_priority(sc: int, saudi: int, impact: int, novelty: int, n_sources: int, credibility: float, age_hours: float, cfg: RankConfig) -> float` (0–100, 1 decimal) and `band_for(priority: float, cfg: RankConfig) -> str` (`"high" | "medium" | "low"`).

- [ ] **Step 1: Write the failing tests**

`tests/test_rank.py`:

```python
import pytest

from sparks.config import RankConfig
from sparks.rank import band_for, compute_priority

CFG = RankConfig()  # defaults from settings.yaml


def test_formula_matches_spec():
    # rubric = .35*9 + .30*10 + .25*8 + .10*7 = 8.85 -> 8.85*7 = 61.95
    # corroboration: 4 sources -> min(3, 4-1)*4 = 12 ; credibility 1.0*6 = 6 ; age 0 -> 12
    p = compute_priority(9, 10, 8, 7, n_sources=4, credibility=1.0, age_hours=0.0, cfg=CFG)
    assert p == pytest.approx(91.95, abs=0.05)


def test_caps_at_100():
    p = compute_priority(10, 10, 10, 10, n_sources=10, credibility=1.0,
                         age_hours=0.0, cfg=CFG)
    assert p <= 100.0


def test_recency_halflife():
    fresh = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=0.0, cfg=CFG)
    day_old = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=24.0, cfg=CFG)
    two_day = compute_priority(5, 5, 5, 5, 1, 0.5, age_hours=48.0, cfg=CFG)
    assert fresh - day_old == pytest.approx(6.0, abs=0.01)   # half of 12
    assert day_old - two_day == pytest.approx(3.0, abs=0.01)  # half again


def test_corroboration_capped():
    three = compute_priority(5, 5, 5, 5, n_sources=4, credibility=0.5, age_hours=0, cfg=CFG)
    ten = compute_priority(5, 5, 5, 5, n_sources=10, credibility=0.5, age_hours=0, cfg=CFG)
    assert ten == pytest.approx(three, abs=0.01)  # cap = 3 extra sources


def test_bands():
    assert band_for(75.0, CFG) == "high"
    assert band_for(74.9, CFG) == "medium"
    assert band_for(50.0, CFG) == "medium"
    assert band_for(49.9, CFG) == "low"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_rank.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.rank'`.

- [ ] **Step 3: Implement `sparks/rank.py`**

```python
"""Composite editorial priority: judge rubric + mechanical signals (spec 4.6)."""
from __future__ import annotations

from sparks.config import RankConfig


def compute_priority(sc: int, saudi: int, impact: int, novelty: int,
                     n_sources: int, credibility: float, age_hours: float,
                     cfg: RankConfig) -> float:
    w = cfg.weights
    rubric = w.sc * sc + w.saudi * saudi + w.impact * impact + w.novelty * novelty  # 0-10
    priority = rubric * cfg.rubric_scale                                            # 0-70
    priority += min(max(n_sources - 1, 0), cfg.corroboration_cap) * cfg.corroboration_points
    priority += max(0.0, min(1.0, credibility)) * cfg.credibility_points
    if age_hours > 0:
        import math
        priority += cfg.recency_points * (0.5 ** (age_hours / cfg.recency_halflife_hours))
    else:
        priority += cfg.recency_points
    return round(min(100.0, priority), 1)


def band_for(priority: float, cfg: RankConfig) -> str:
    if priority >= cfg.high_band:
        return "high"
    if priority >= cfg.medium_band:
        return "medium"
    return "low"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_rank.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/rank.py tests/test_rank.py
git commit -m "feat: composite priority ranker"
```

---

### Task 11: Pipeline cycle (orchestration)

**Files:**
- Create: `sparks/pipeline.py`
- Modify: `sparks/fetch/runner.py` (add `ContentFetcher`), `sparks/db.py` (add `unextracted_items()`, `all_stories()`)
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `run_cycle(settings, db=None, fetch_runner=None, content_fetcher=None, judge_service=None) -> CycleReport`; `ContentFetcher(settings, db, client=None).fetch_article(item: ItemRecord) -> bool` (fetches the item's own URL politely, saves raw, extracts, updates the item; returns False on failure); `Database.unextracted_items() -> list[ItemRecord]`; `Database.all_stories() -> list[StoryRecord]`.

Why a second fetch stage: RSS/listing raw files contain the *feed*, not the article. Items get real article text via `ContentFetcher` (per-item polite fetch of `item.url`, raw saved, `item.raw_path` updated to the article file).

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sparks.config import load_settings
from sparks.db import Database
from sparks.judge.schema import JudgeOutput
from sparks.models import FetchedEntry, Source, SourceRun
from sparks.pipeline import run_cycle

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

VALID = JudgeOutput(supply_chain_relevance=9, saudi_gcc_relevance=10, market_impact=8,
                    novelty=7, rationale_supply_chain="r", rationale_saudi_gcc="r",
                    rationale_market_impact="r", rationale_novelty="r",
                    suggested_category="ports-shipping", gist="Mawani expands Jeddah.")


class FakeJudge:
    def judge(self, ctx, settings=None):
        return VALID


class FakeFetchRunner:
    """Inserts 3 feed items: two near-duplicates + one distinct."""
    def __init__(self, settings, db):
        self.settings, self.db = settings, db

    def run(self, sources=None):
        sid = self.db.upsert_source(Source(name="Ex", kind="rss",
                                           url="https://feed.example/rss"))
        entries = [
            FetchedEntry("https://pub.com/a", "Jeddah terminal expansion announced", NOW),
            FetchedEntry("https://pub.com/b", "Jeddah terminal expansion announced!", NOW),
            FetchedEntry("https://pub.com/c", "Dammam warehouses at record occupancy", NOW),
        ]
        run = SourceRun(source_id=sid, source_name="Ex", status="ok",
                        items_found=3, items_new=0)
        for e in entries:
            if self.db.insert_item(sid, e, raw_path="pending", fetched_at=NOW):
                run.items_new += 1
        return [run]


class FakeContentFetcher:
    """Fills extraction from fixture files without network."""
    def __init__(self, settings, db):
        self.settings, self.db = settings, db

    def fetch_article(self, item):
        good = (FIXTURES / "article_good.html").read_text(encoding="utf-8")
        from sparks.extract import extract_article
        extracted = extract_article(good)
        self.db.update_item_extraction(item.id, extracted.text, None, extracted.word_count)
        return True


@pytest.fixture
def pipeline_settings(settings):
    return settings


def test_run_cycle_full_happy_path(settings):
    db = Database(settings.db_path)
    report = run_cycle(settings, db=db,
                       fetch_runner=FakeFetchRunner(settings, db),
                       content_fetcher=FakeContentFetcher(settings, db),
                       api_judge=FakeJudge(), local_judge=FakeJudge())
    assert report.finished_at is not None
    assert report.items_new == 3
    assert report.stories_created == 2      # near-duplicates merged
    assert report.stories_judged >= 1
    assert report.stories_ranked >= 1
    queue = db.queue_stories()
    assert len(queue) == 2
    top = queue[0]
    assert top.band in ("high", "medium")
    assert top.judge_status in ("api", "local")
    assert top.n_sources == 2              # merged cluster


def test_run_cycle_isolates_fetch_errors(settings):
    class ExplodingRunner:
        def run(self, sources=None):
            run = SourceRun(source_id=1, source_name="Boom", status="error", items_found=0,
                            error="HTTPError: 500")
            return [run]

    db = Database(settings.db_path)
    report = run_cycle(settings, db=db, fetch_runner=ExplodingRunner(),
                       content_fetcher=FakeContentFetcher(settings, db))
    assert report.errors == ["HTTPError: 500"]
    assert report.stories_created == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.pipeline'`.

- [ ] **Step 3: Add `unextracted_items()` and `all_stories()` to `sparks/db.py`**

Inside `class Database` (after `update_item_extraction` and after `queue_stories` respectively):

```python
    def unextracted_items(self) -> list[ItemRecord]:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE extracted_text IS NULL AND status != 'failed'"
            " ORDER BY id").fetchall()
        return [self._row_to_item(r) for r in rows]

    def all_stories(self) -> list[StoryRecord]:
        rows = self.conn.execute("SELECT * FROM stories ORDER BY id").fetchall()
        return [self._row_to_story(r) for r in rows]
```

- [ ] **Step 4: Add `ContentFetcher` to `sparks/fetch/runner.py`**

Append to the module (reuses the politeness/robots helpers as module-level functions — refactor `_polite_wait`/`_robots_allows` logic into `class _Politeness` shared by both classes, or simplest: duplicate the three small helpers in `ContentFetcher`; duplication of 20 lines is acceptable here and avoids churn):

```python
class ContentFetcher:
    """Second-stage fetch: per-item article pages -> raw + extracted text."""

    def __init__(self, settings: Settings, db: Database, client: httpx.Client | None = None):
        self.settings = settings
        self.db = db
        self._client = client
        self._domain_last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                headers={"User-Agent": self.settings.fetch.user_agent,
                         "Accept-Language": "en, ar;q=0.8"},
                timeout=self.settings.fetch.timeout_seconds, follow_redirects=True)
        return self._client

    def fetch_article(self, item: ItemRecord) -> bool:
        if not self._robots_allows(item.url):
            self.db.update_item_status(item.id, "failed")
            return False
        try:
            self._polite_wait(item.url.split("/")[2] if "://" in item.url else item.url)
            resp = self.client.get(item.url)
            resp.raise_for_status()
            raw_path = save_raw(self.settings.raw_dir, item.url, resp.content)
            from sparks.extract import extract_article
            extracted = extract_article(resp.content.decode("utf-8", errors="replace"))
            if extracted is None:
                self.db.update_item_status(item.id, "failed")
                return False
            self.conn_update(item, raw_path, extracted)
            return True
        except Exception:
            self.db.update_item_status(item.id, "failed")
            return False

    def conn_update(self, item: ItemRecord, raw_path: pathlib.Path,
                    extracted) -> None:
        self.db.conn.execute(
            "UPDATE items SET raw_path=?, extracted_text=?, language=?, word_count=?,"
            " status='extracted' WHERE id=?",
            (str(raw_path), extracted.text, extracted.language, extracted.word_count,
             item.id))
        self.db.conn.commit()

    # _polite_wait / _robots_allows / _robots_cache: same logic as FetchRunner
```

Write the three helper methods out in full — copy the bodies from `FetchRunner`; they are identical. Also add `ItemRecord` to the module's `from sparks.models import ...` line (the type hint needs it).

- [ ] **Step 5: Implement `sparks/pipeline.py`**

```python
"""Pipeline orchestration: fetch -> content -> extract -> cluster -> judge -> rank."""
from __future__ import annotations

from datetime import datetime, timezone

from sparks.config import Settings
from sparks.db import Database
from sparks.dedupe import build_clusters
from sparks.fetch.runner import ContentFetcher, FetchRunner
from sparks.judge.service import JudgeService
from sparks.models import CycleReport
from sparks.rank import band_for, compute_priority


def run_cycle(settings: Settings, db: Database | None = None,
              fetch_runner=None, content_fetcher=None, judge_service=None,
              api_judge=None, local_judge=None) -> CycleReport:
    db = db or Database(settings.db_path)
    report = CycleReport(started_at=datetime.now(timezone.utc))
    runner = fetch_runner or FetchRunner(settings, db)
    fetcher = content_fetcher or ContentFetcher(settings, db)

    runs = runner.run()
    report.runs = runs
    report.errors = [r.error for r in runs if r.error]
    report.items_new = sum(r.items_new for r in runs)

    for item in db.unextracted_items():
        fetcher.fetch_article(item)

    all_items = db.window_items(days=7, extracted_only=True)
    clustered_ids = {it.id for it in all_items if it.story_id is not None}
    for cluster in build_clusters(all_items):
        if cluster.primary_item_id in clustered_ids:
            continue  # story already exists for this cluster
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
        report.stories_created += 1

    service = judge_service or JudgeService(settings, db, api_judge=api_judge,
                                            local_judge=local_judge)
    judged, unscored = service.judge_pending()
    report.stories_judged = judged
    report.stories_unscored = unscored

    report.stories_ranked = _rank_all(db, settings)
    report.finished_at = datetime.now(timezone.utc)
    return report


def _rank_all(db: Database, settings: Settings) -> int:
    now = datetime.now(timezone.utc)
    ranked = 0
    for story in db.all_stories():
        row = db.latest_judge(story.id)
        if row is None or story.judge_status not in ("api", "local"):
            continue
        members = db.story_members(story.id)
        times = [m.published_at or m.fetched_at for m in members if
                 (m.published_at or m.fetched_at)]
        age_hours = max(0.0, (now - max(times)).total_seconds() / 3600) if times else 0.0
        priority = compute_priority(
            row.supply_chain_relevance, row.saudi_gcc_relevance, row.market_impact,
            row.novelty, n_sources=len(members),
            credibility=db.story_max_credibility(story.id),
            age_hours=age_hours, cfg=settings.rank)
        db.set_story_ranking(story.id, priority=priority, band=band_for(priority, settings.rank),
                             category=row.suggested_category)
        ranked += 1
    return ranked
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 2 PASSED.

- [ ] **Step 7: Commit**

```bash
git add sparks/pipeline.py sparks/fetch/runner.py sparks/db.py tests/test_pipeline.py
git commit -m "feat: full pipeline cycle with per-source isolation"
```

---

### Task 12: Replay from raw

**Files:**
- Modify: `sparks/pipeline.py` (add `replay`)
- Test: `tests/test_pipeline.py` (append replay tests)

**Interfaces:**
- Consumes: `Database.wipe_derived()` (Task 2), extraction/clustering/judging/ranking from Tasks 5–11.
- Produces: `replay(settings, db=None, skip_judge: bool = False, api_judge=None, local_judge=None) -> CycleReport` — wipes derived state, re-extracts every item from its raw file, re-clusters, restores cached judge verdicts by primary URL key (no re-judging unless missing and `skip_judge=False`), re-ranks with current config.

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_pipeline.py`:

```python
from sparks.pipeline import replay


def _seed_cycle(settings, db):
    """Run a cycle with fixture-backed raw files so replay can re-read them."""
    import shutil
    sid = db.upsert_source(Source(name="Ex", kind="rss", url="https://feed.example/rss"))
    good_bytes = (FIXTURES / "article_good.html").read_bytes()
    variant_bytes = (FIXTURES / "article_variant.html").read_bytes()
    from sparks.fetch.runner import save_raw
    raw_good = save_raw(settings.raw_dir, "https://pub.com/a", good_bytes)
    raw_variant = save_raw(settings.raw_dir, "https://pub.com/b", variant_bytes)
    for url, title, raw in [
        ("https://pub.com/a", "Jeddah terminal expansion announced", raw_good),
        ("https://pub.com/b", "Jeddah terminal expansion announced!", raw_variant),
    ]:
        iid = db.insert_item(sid, FetchedEntry(url, title, NOW), str(raw), NOW)
        db.update_item_extraction(iid, (FIXTURES / "article_good.html").read_text("utf-8"),
                                  None, 200)  # placeholder; replay overwrites from raw
    from sparks.dedupe import build_clusters
    items = db.window_items(days=7)
    for cluster in build_clusters(items):
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
    from sparks.judge.service import JudgeService
    service = JudgeService(settings, db, api_judge=FakeJudge(), local_judge=FakeJudge())
    service.judge_pending()
    from sparks.pipeline import _rank_all
    _rank_all(db, settings)  # give the story a ranked priority so replay can change it


def test_replay_reuses_judge_cache_and_reranks(settings):
    db = Database(settings.db_path)
    _seed_cycle(settings, db)
    old_priority = db.queue_stories()[0].priority

    settings.rank.rubric_scale = 5.0  # change config, expect different priorities
    report = replay(settings, db=db, skip_judge=True)

    queue = db.queue_stories()
    assert len(queue) == 1                      # the two items re-merged into one story
    assert queue[0].priority != old_priority
    assert db.latest_judge(queue[0].id).gist == "Mawani expands Jeddah."  # cache restored
    assert report.stories_ranked == 1


def test_replay_reextracts_from_raw(settings):
    db = Database(settings.db_path)
    _seed_cycle(settings, db)
    db.wipe_derived()
    assert db.window_items(days=7)[0].extracted_text is None
    replay(settings, db=db, skip_judge=True)
    items = db.window_items(days=7)
    assert all(i.extracted_text and "Jeddah" in i.extracted_text for i in items)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -k replay -v`
Expected: FAIL — `ImportError: cannot import name 'replay'`.

- [ ] **Step 3: Implement `replay` in `sparks/pipeline.py`**

```python
def replay(settings: Settings, db: Database | None = None, skip_judge: bool = False,
           api_judge=None, local_judge=None) -> CycleReport:
    """Rebuild stories/judgments/rankings from raw files with current config.

    Judge verdicts are cached by the primary item's url_key and restored when the
    same story re-clusters, so config iterations cost nothing. Missing verdicts are
    re-judged unless skip_judge=True."""
    db = db or Database(settings.db_path)
    report = CycleReport(started_at=datetime.now(timezone.utc))

    cache: dict[str, object] = {}
    for story in db.all_stories():
        row = db.latest_judge(story.id)
        if row is None:
            continue
        primary = next((m for m in db.story_members(story.id)
                        if m.id == story.primary_item_id), None)
        if primary:
            cache[primary.url_key] = row

    db.wipe_derived()

    from sparks.extract import extract_article
    for item in db.window_items(days=3650):
        try:
            html = pathlib.Path(item.raw_path).read_text(encoding="utf-8",
                                                          errors="replace")
            extracted = extract_article(html)
        except OSError:
            continue
        if extracted is not None:
            db.update_item_extraction(item.id, extracted.text, extracted.language,
                                      extracted.word_count)

    all_items = db.window_items(days=3650)
    for cluster in build_clusters(all_items):
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
        report.stories_created += 1
        primary = next(m for m in all_items if m.id == cluster.primary_item_id)
        cached = cache.get(primary.url_key)
        if cached is not None:
            db.save_judge_score(story_id, tier=cached.tier, model=cached.model,
                                prompt_version=cached.prompt_version, output=cached)
            db.set_story_judge_status(story_id, cached.tier)

    if not skip_judge:
        service = JudgeService(settings, db, api_judge=api_judge, local_judge=local_judge)
        judged, unscored = service.judge_pending()
        report.stories_judged, report.stories_unscored = judged, unscored

    report.stories_ranked = _rank_all(db, settings)
    report.finished_at = datetime.now(timezone.utc)
    return report
```

Add `import pathlib` to the module imports. `save_judge_score(output=cached)` works because it reads the ten attribute names `JudgeScoreRow` also carries.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: 4 PASSED (2 cycle + 2 replay).

- [ ] **Step 5: Commit**

```bash
git add sparks/pipeline.py tests/test_pipeline.py
git commit -m "feat: replay derived state from raw files with judge cache"
```

---

### Task 13: CLI

**Files:**
- Create: `sparks/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_settings`, `Database`, `run_cycle`, `replay`, `Source` models, `sources.yaml`.
- Produces: `main(argv: list[str] | None = None) -> int` with subcommands `init`, `fetch`, `queue [-n N] [--band {high,medium,low}]`, `replay [--skip-judge]`, `sources list|add`. Registered as console script `sparks`.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
import yaml
from datetime import datetime, timezone

from sparks.cli import main
from sparks.db import Database
from sparks.models import CycleReport, FetchedEntry, Source

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_init_seeds_sources(settings, capsys):
    assert main(["init"]) == 0
    db = Database(settings.db_path)
    from sparks.cli import SOURCES_SEED
    expected = len(yaml.safe_load(SOURCES_SEED.read_text(encoding="utf-8"))["sources"])
    assert len(db.all_sources(enabled_only=False)) == expected
    assert "seeded" in capsys.readouterr().out


def test_sources_add_and_list(settings, capsys):
    assert main(["sources", "add", "--kind", "rss", "--name", "My Feed",
                 "--url", "https://my.example/rss", "--credibility", "0.7"]) == 0
    assert main(["sources", "list"]) == 0
    out = capsys.readouterr().out
    assert "My Feed" in out and "rss" in out


def test_queue_prints_ranked_stories(settings, capsys):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="S", kind="rss", url="https://s.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://s.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    story_id = db.create_story("Jeddah expansion", iid)
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, 88.0, "high", "ports-shipping")
    db.close()
    assert main(["queue"]) == 0
    out = capsys.readouterr().out
    assert "Jeddah expansion" in out and "88" in out and "HIGH" in out


def test_fetch_invokes_pipeline(settings, capsys, monkeypatch):
    import sparks.cli as cli

    def fake_report():
        return CycleReport(started_at=NOW, finished_at=NOW, items_new=5,
                           stories_created=2, stories_judged=2, stories_ranked=2)

    monkeypatch.setattr(cli, "run_cycle", lambda s: fake_report())
    assert main(["fetch"]) == 0
    out = capsys.readouterr().out
    assert "items_new=5" in out and "stories_ranked=2" in out


def test_replay_invokes_pipeline(settings, capsys, monkeypatch):
    import sparks.cli as cli
    monkeypatch.setattr(cli, "replay",
                        lambda s, skip_judge=False: CycleReport(started_at=NOW))
    assert main(["replay", "--skip-judge"]) == 0
    assert "replay" in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.cli'`.

- [ ] **Step 3: Implement `sparks/cli.py`**

```python
"""sparks CLI: init | fetch | queue | replay | sources."""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

from sparks.config import REPO_ROOT, Settings, load_settings
from sparks.db import Database
from sparks.models import CycleReport, Source
from sparks.pipeline import replay, run_cycle

SOURCES_SEED = REPO_ROOT / "sources.yaml"


def _db(settings: Settings) -> Database:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Database(settings.db_path)


def cmd_init(args, settings: Settings) -> int:
    db = _db(settings)
    data = yaml.safe_load(SOURCES_SEED.read_text(encoding="utf-8")) or {}
    count = 0
    for raw in data.get("sources", []):
        db.upsert_source(Source(name=raw["name"], kind=raw["kind"], url=raw["url"],
                                credibility=float(raw.get("credibility", 0.5)),
                                category_hint=raw.get("category_hint"),
                                link_pattern=raw.get("link_pattern")))
        count += 1
    print(f"seeded {count} sources from {SOURCES_SEED}")
    return 0


def cmd_fetch(args, settings: Settings) -> int:
    report: CycleReport = run_cycle(settings)
    errors = f" errors={len(report.errors)}" if report.errors else ""
    print(f"fetch done: items_new={report.items_new} "
          f"stories_created={report.stories_created} "
          f"stories_judged={report.stories_judged} "
          f"stories_ranked={report.stories_ranked}{errors}")
    for err in report.errors:
        print(f"  error: {err}", file=sys.stderr)
    return 1 if report.errors else 0


def cmd_queue(args, settings: Settings) -> int:
    db = _db(settings)
    stories = db.queue_stories(limit=args.n, band=args.band)
    if not stories:
        print("queue is empty — run `sparks fetch` first")
        return 0
    for s in stories:
        print(f"{s.band.upper():6} {s.priority:5.1f}  {s.category or '-':20} "
              f"{s.title}  ({s.n_sources} sources)")
    return 0


def cmd_replay(args, settings: Settings) -> int:
    report = replay(settings, skip_judge=args.skip_judge)
    print(f"replay done: stories_created={report.stories_created} "
          f"stories_ranked={report.stories_ranked} "
          f"stories_judged={report.stories_judged}")
    return 0


def cmd_sources(args, settings: Settings) -> int:
    db = _db(settings)
    if args.sources_cmd == "add":
        db.upsert_source(Source(name=args.name, kind=args.kind, url=args.url,
                                credibility=args.credibility,
                                category_hint=args.category_hint,
                                link_pattern=args.link_pattern))
        print(f"added source {args.name}")
    else:
        for s in db.all_sources(enabled_only=False):
            health = "ok" if s.healthy else "unhealthy"
            print(f"{s.kind:5} {health:10} cred={s.credibility:.1f}  {s.name}  {s.url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sparks")
    parser.add_argument("--settings", default=None, help="path to settings.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("fetch")
    q = sub.add_parser("queue")
    q.add_argument("-n", type=int, default=50)
    q.add_argument("--band", choices=["high", "medium", "low"], default=None)
    r = sub.add_parser("replay")
    r.add_argument("--skip-judge", action="store_true")
    s = sub.add_parser("sources")
    s_sub = s.add_subparsers(dest="sources_cmd", required=True)
    s_sub.add_parser("list")
    a = s_sub.add_parser("add")
    a.add_argument("--kind", choices=["rss", "html"], required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--credibility", type=float, default=0.5)
    a.add_argument("--category-hint", default=None)
    a.add_argument("--link-pattern", default=None)

    args = parser.parse_args(argv)
    settings = load_settings(pathlib.Path(args.settings) if args.settings else None)
    handlers = {"init": cmd_init, "fetch": cmd_fetch, "queue": cmd_queue,
                "replay": cmd_replay, "sources": cmd_sources}
    return handlers[args.cmd](args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest -v`
Expected: all tests across the 14 test files PASS (≈55 tests).

- [ ] **Step 5: Manual smoke check**

```bash
sparks init
sparks sources list
sparks fetch          # hits the real network; verify queue output looks sane
sparks queue -n 10
```

If `SPARKS_API_KEY` is unset, the API tier fails and the local tier is used only if Ollama is running; otherwise stories are marked `unscored` — verify `sparks queue` still shows previously ranked items and does not crash.

- [ ] **Step 6: Commit**

```bash
git add sparks/cli.py tests/test_cli.py
git commit -m "feat: sparks CLI (init/fetch/queue/replay/sources)"
```

---

## Plan 1 completion checklist

After Task 13, the engine is complete per spec sections 4–5, 9, 11 (pipeline parts), and 15 (success criterion 4 partially — headless). What is deliberately **not** here: dashboard UI, generation prompts, fact-check, publishing, packaging (Plan 2); public site (Plan 3).





