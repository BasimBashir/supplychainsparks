# Supply Chain Sparks — Plan 2: Desktop App & Editorial Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `SupplyChainSparks.exe` — the local Windows app around the Plan 1 engine: FastAPI local server, scheduled + manual fetching, LLM content generation (article/LinkedIn, EN + AR), fact-check gating, git publishing to the content repo, and a React editorial dashboard (Queue / Story detail / Review / Published) in a tray-resident pywebview shell, packaged with PyInstaller + Inno Setup.

**Architecture:** The Plan 1 `sparks` package gains a `server/` layer (FastAPI + background job runner), a `generate/` layer (versioned prompts → API model → pydantic outputs → DB), a `factcheck/` layer (claim verification against source texts, gating approval), and a `publish/` layer (dulwich git publisher writing the content contract). A Vite React dashboard in `dashboard/` is built to static files and served by the local server. `sparks/app/` is the desktop shell: single-instance lock, uvicorn in a thread, APScheduler, tray icon, webview window.

**Tech Stack:** Python 3.11+ (Plan 1 deps) + fastapi, uvicorn, apscheduler, pystray, pillow, pywebview, dulwich. Frontend: Vite + React 18 (JS/JSX), vitest + @testing-library/react + jsdom (dev).

**Spec:** `docs/superpowers/specs/2026-09-08-supply-chain-sparks-design.md`
**Depends on:** Plan 1 complete (`sparks` engine: config, db, models, pipeline, judge).

## Global Constraints

- Same floors as Plan 1: Windows 10/11, CPU-only, 8 GB RAM; the app runs without Ollama; the public site never depends on this PC.
- **New dependencies (amends Plan 1's list):** runtime `fastapi, uvicorn[standard], apscheduler>=3.10, pystray, pillow, pywebview, dulwich`; frontend dev `vitest, @testing-library/react, @testing-library/jest-dom, jsdom` (npm). Engine-only installs (`pip install -e .`) must still work without the app extras — put new runtime deps under `[project.optional-dependencies] app = [...]`.
- No network in automated tests. Git publisher tests use local bare repositories via dulwich (file paths). Ollama ping and external APIs are mocked.
- Server binds `127.0.0.1` only; every `/api/*` route requires the `X-Sparks-Token` header (token generated on first run, persisted in the DB `settings_kv` table).
- **Published-content hard constraints (spec §6):** generation prompts forbid source names/links/invented facts; `assert_publishable()` mechanically re-checks every generation before it can be approved (URL patterns + explicit source-name blocklist from the DB).
- Source attribution (names, URLs) is shown in the dashboard but NEVER written into `meta.json`, `en.md`, `ar.md`, or LinkedIn text.
- **Content repo contract (identical to Plan 3 — do not diverge):**
  ```
  content/posts/<slug>/en.md      # English body, markdown, no H1
  content/posts/<slug>/ar.md      # Arabic body, markdown, no H1
  content/posts/<slug>/meta.json  # {
                                   #   "slug": "saudi-port-expansion-2026",
                                   #   "title": "...", "titleAr": "...",
                                   #   "description": "...", "descriptionAr": "...",
                                   #   "category": "ports-shipping",
                                   #   "tags": ["Jeddah", "Mawani"],
                                   #   "publishedAt": "2026-09-08T14:30:00Z",
                                   #   "priority": 91.2
                                   # }
  ```
- TDD: red → green → commit per task. Commits: `feat|fix|test|chore: ...`.
- Datetimes: aware UTC ISO-8601.

## File Structure

```
supplychainsparks/
├── pyproject.toml                      # + [project.optional-dependencies] app
├── settings.yaml                       # + server:, fetch.schedule_hours, publish:, writer model alias
├── dashboard/                          # Vite React app (built to dashboard/dist, served by FastAPI)
│   ├── package.json  vite.config.js  index.html
│   └── src/
│       ├── main.jsx  App.jsx  api.js  styles.css
│       ├── views/QueueView.jsx  StoryDetail.jsx  ReviewView.jsx  PublishedView.jsx  Wizard.jsx
│       └── tests/QueueView.test.jsx  ReviewView.test.jsx
├── sparks/
│   ├── judge/api.py                    # MODIFY: rename _parse_content -> parse_json_content (public)
│   ├── context.py                      # NEW: story_context(db, story) shared by judge + generation
│   ├── server/
│   │   ├── __init__.py  app.py         # create_app(settings), token middleware, static mount
│   │   ├── jobs.py                     # JobRunner: ThreadPoolExecutor + status registry
│   │   └── routes.py                   # /api/* endpoints (stories, sources, generate, flags, publish, settings)
│   ├── generate/
│   │   ├── __init__.py  schema.py      # GeneratedArticle, LinkedInPost, SeoBlock (+ to_markdown/to_text)
│   │   ├── prompt.py                   # render_generation_prompt(kind, language, ctx)
│   │   ├── validate.py                 # assert_publishable(text, blocked_names) -> list[str]
│   │   └── service.py                  # GenerationService.generate_for_story(...)
│   ├── factcheck/
│   │   ├── __init__.py  service.py     # FactCheckService.check_generation(...)
│   ├── prompts/
│   │   ├── article_en_v1.md  article_ar_v1.md
│   │   ├── linkedin_en_v1.md  linkedin_ar_v1.md
│   │   └── factcheck_v1.md
│   ├── publish/
│   │   ├── __init__.py  git.py         # GitPublisher (dulwich clone/write/commit/push)
│   │   └── content.py                  # build_post_files() -> contract files dict
│   └── app/
│       ├── __init__.py  main.py        # run(): single-instance, uvicorn thread, webview, tray
│       ├── scheduler.py                # FetchScheduler (APScheduler interval)
│       └── tray.py                     # build_tray(on_open, on_fetch, on_quit) -> pystray Icon
├── scripts/build.ps1                   # dashboard build + pyinstaller + inno setup
├── installer.iss                       # Inno Setup script
├── sparks_exe.spec                     # PyInstaller spec
└── tests/
    ├── test_server_app.py  test_server_routes.py  test_server_jobs.py
    ├── test_db_publications.py  test_generate_schema.py  test_generate_prompt.py
    ├── test_generate_validate.py  test_generate_service.py  test_factcheck.py
    ├── test_publish_git.py  test_publish_content.py  test_app_scheduler.py
    └── test_app_lock.py
```

**Interface contract:**
- `sparks.server.app.create_app(settings, db=None, job_runner=None) -> FastAPI`
- `sparks.server.jobs.JobRunner` — `.submit(name, fn, *a) -> job_id`, `.status(job_id) -> dict`
- `sparks.context.story_context(db, story) -> StoryContext` (moved out of JudgeService; JudgeService refactored to call it — Plan 1 tests must stay green)
- `sparks.generate.service.GenerationService(settings, db, api_judge=None).generate_for_story(story_id, formats=("article", "linkedin")) -> list[int]` (generation ids)
- `sparks.factcheck.service.FactCheckService(settings, db, api_judge=None).check_generation(generation_id) -> int` (flag count)
- `sparks.publish.git.GitPublisher(settings).publish(files: dict[str, str], message: str) -> str` (commit sha)
- `sparks.publish.content.build_post_files(meta: dict, en_md: str, ar_md: str) -> dict[str, str]`
- `sparks.app.scheduler.FetchScheduler(settings, job_runner).start() / .shutdown()`
- `sparks.app.main.run() -> int` (entry `sparks-app` console script)

---

### Task 1: FastAPI server scaffold + token auth

**Files:**
- Modify: `pyproject.toml` (app extras + `sparks-app` entry)
- Create: `sparks/server/__init__.py` (empty), `sparks/server/app.py`
- Test: `tests/test_server_app.py`

**Interfaces:**
- Consumes: `Settings`, `Database` (Plan 1).
- Produces: `create_app(settings, db=None) -> FastAPI` with `GET /api/health`; auth middleware rejecting missing/wrong `X-Sparks-Token`; token bootstrap via `db.get_setting/set_setting`.

- [ ] **Step 1: Add dependencies and config**

`pyproject.toml` — extend:

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0", "respx>=0.21"]
app = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "apscheduler>=3.10",
    "pystray>=0.19",
    "pillow>=10.0",
    "pywebview>=5.0",
    "dulwich>=0.22",
]

[project.scripts]
sparks = "sparks.cli:main"
sparks-app = "sparks.app.main:run"
```

`settings.yaml` — append:

```yaml
server:
  host: "127.0.0.1"
  port: 8765

fetch:
  schedule_hours: 6        # automated fetch interval; 0 disables scheduling

publish:
  repo_url: ""             # https://github.com/<org>/<content-repo>.git
  branch: "main"
  token: "env:SPARKS_GIT_TOKEN"
  site_base_url: "https://supplychainsparks.com"
```

(Note: `fetch` already exists in settings.yaml — merge these keys into the existing `fetch:` block; do not create a second one.)

**Also extend `sparks/config.py` in this task** (later tasks depend on these fields):

```python
@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class PublishConfig:
    repo_url: str = ""
    branch: str = "main"
    token: str = ""
    site_base_url: str = "https://supplychainsparks.com"
```

Add `server: ServerConfig`, `publish: PublishConfig` fields to `Settings`; add `schedule_hours: float = 6.0` to `FetchConfig`; parse `raw.get("server")` and `raw.get("publish")` in `load_settings` the same way as `fetch`. Extend `tests/test_config.py` with:

```python
def test_server_and_publish_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path))
    s = load_settings(repo_settings_path())
    assert s.server.host == "127.0.0.1" and s.server.port == 8765
    assert s.publish.branch == "main"
    assert s.fetch.schedule_hours == 6
```

- [ ] **Step 2: Add `get_setting`/`set_setting` to `sparks/db.py`**

Inside `class Database`:

```python
    # -- settings kv ----------------------------------------------------------
    def get_setting(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM settings_kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings_kv (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        self.conn.commit()
```

- [ ] **Step 3: Write the failing tests**

`tests/test_server_app.py`:

```python
import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


@pytest.fixture
def client(settings, tmp_path):
    db = Database(settings.db_path)
    app = create_app(settings, db=db)
    return TestClient(app), db


def test_health_requires_token(client):
    tc, db = client
    assert tc.get("/api/health").status_code == 401
    token = db.get_setting("server_token")
    assert token  # generated on first app creation
    r = tc.get("/api/health", headers={"X-Sparks-Token": token})
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_wrong_token_rejected(client):
    tc, db = client
    assert tc.get("/api/health", headers={"X-Sparks-Token": "nope"}).status_code == 401


def test_token_stable_across_apps(settings, tmp_path):
    db1 = Database(settings.db_path)
    create_app(settings, db=db1)
    token = db1.get_setting("server_token")
    db2 = Database(settings.db_path)
    create_app(settings, db=db2)
    assert db2.get_setting("server_token") == token
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `pip install -e ".[app,dev]"` then `python -m pytest tests/test_server_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.server'`.

- [ ] **Step 5: Implement `sparks/server/app.py`**

```python
"""Local FastAPI app: token-gated API + static dashboard."""
from __future__ import annotations

import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from sparks.config import Settings
from sparks.db import Database


def _server_token(db: Database) -> str:
    token = db.get_setting("server_token")
    if not token:
        token = secrets.token_urlsafe(24)
        db.set_setting("server_token", token)
    return token


def create_app(settings: Settings, db: Database | None = None) -> FastAPI:
    db = db or Database(settings.db_path)
    token = _server_token(db)
    app = FastAPI(title="Supply Chain Sparks", docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def check_token(request: Request, call_next):
        if request.url.path.startswith("/api"):
            if request.headers.get("X-Sparks-Token") != token:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    app.state.settings = settings
    app.state.db = db

    dashboard_dist = settings.settings_path.parent / "dashboard" / "dist"
    if dashboard_dist.exists():
        app.mount("/", StaticFiles(directory=dashboard_dist, html=True), name="dashboard")
    return app
```

(Static mount is a convenience for packaged builds; in dev the Vite dev server proxies to the API.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_server_app.py -v`
Expected: 3 PASSED.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml settings.yaml sparks/server/ sparks/db.py tests/test_server_app.py
git commit -m "feat: local fastapi server with token auth"
```

---

### Task 2: Publications data model (generations, flags, publications, users)

**Files:**
- Modify: `sparks/db.py` (new tables + methods)
- Test: `tests/test_db_publications.py`

**Interfaces:**
- Consumes: Plan 1 schema.
- Produces: `save_generation(...) -> int`, `generations_for(story_id) -> list[dict]`, `update_generation_content(gen_id, content)`, `replace_fact_flags(gen_id, flags: list[dict])`, `open_flags(story_id) -> list[dict]`, `resolve_flag(flag_id, resolution)`, `create_publication(story_id, destination, url, commit_sha, detail) -> int`, `list_publications() -> list[dict]`, `set_story_status(story_id, status)`, `get_story(story_id) -> StoryRecord | None`, `all_source_names() -> list[str]`.

- [ ] **Step 1: Write the failing tests**

`tests/test_db_publications.py`:

```python
from datetime import datetime, timezone

import pytest

from sparks.db import Database
from sparks.models import FetchedEntry, Source

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


@pytest.fixture
def seeded(settings):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Story", NOW), "raw", NOW)
    story_id = db.create_story("Story", iid)
    return db, story_id


def test_generation_roundtrip_and_flags(seeded):
    db, story_id = seeded
    gen_id = db.save_generation(
        story_id=story_id, format="article", language="en", model="glm-4-flash",
        prompt_version="article_en_v1",
        content="# Head\n\nBody", seo_slug="story", seo_description="d",
        seo_tags='["a","b"]')
    gens = db.generations_for(story_id)
    assert gens[0]["id"] == gen_id and gens[0]["language"] == "en"
    db.update_generation_content(gen_id, "# Edited")
    assert db.generations_for(story_id)[0]["content"] == "# Edited"

    db.replace_fact_flags(gen_id, [
        {"claim": "2m TEU", "verdict": "supported", "source_snippet": "two million TEU"},
        {"claim": "by 2031", "verdict": "unsupported", "source_snippet": ""},
    ])
    flags = db.open_flags(story_id)
    assert len(flags) == 1 and flags[0]["verdict"] == "unsupported"
    db.resolve_flag(flags[0]["id"], "resolved_edit")
    assert db.open_flags(story_id) == []


def test_publications_and_status_flow(seeded):
    db, story_id = seeded
    db.set_story_status(story_id, "review")
    assert db.get_story(story_id).status == "review"
    pub_id = db.create_publication(story_id, "site",
                                   url="https://supplychainsparks.com/post/story",
                                   commit_sha="abc123", detail="en+ar")
    pubs = db.list_publications()
    assert pubs[0]["id"] == pub_id and "supplychainsparks.com" in pubs[0]["url"]
    assert pubs[0]["published_at"]


def test_source_names(seeded):
    db, _ = seeded
    assert db.all_source_names() == ["Reuters"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_db_publications.py -v`
Expected: FAIL — `AttributeError: 'Database' object has no attribute 'save_generation'`.

- [ ] **Step 3: Implement — extend `SCHEMA` in `sparks/db.py` and add methods**

Append to the `SCHEMA` string:

```sql
CREATE TABLE IF NOT EXISTS generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    format TEXT NOT NULL CHECK (format IN ('article', 'linkedin')),
    language TEXT NOT NULL CHECK (language IN ('en', 'ar')),
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    content TEXT NOT NULL,
    seo_slug TEXT, seo_description TEXT, seo_tags TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS fact_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generation_id INTEGER NOT NULL REFERENCES generations(id),
    claim TEXT NOT NULL,
    verdict TEXT NOT NULL,
    source_snippet TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id INTEGER NOT NULL REFERENCES stories(id),
    destination TEXT NOT NULL CHECK (destination IN ('site', 'linkedin')),
    url TEXT, commit_sha TEXT, detail TEXT,
    published_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

(`CREATE TABLE IF NOT EXISTS` means existing DBs upgrade in place — bump `SCHEMA_VERSION` to 2.)

Methods on `Database`:

```python
    # -- generations / flags / publications -------------------------------
    def save_generation(self, story_id: int, format: str, language: str, model: str,
                        prompt_version: str, content: str, seo_slug: str | None = None,
                        seo_description: str | None = None,
                        seo_tags: str | None = None) -> int:
        cur = self.conn.execute(
            """INSERT INTO generations (story_id, format, language, model,
               prompt_version, content, seo_slug, seo_description, seo_tags)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (story_id, format, language, model, prompt_version, content,
             seo_slug, seo_description, seo_tags))
        self.conn.commit()
        return cur.lastrowid

    def generations_for(self, story_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM generations WHERE story_id=? ORDER BY id", (story_id,)).fetchall()
        return [dict(r) for r in rows]

    def update_generation_content(self, gen_id: int, content: str) -> None:
        self.conn.execute("UPDATE generations SET content=? WHERE id=?", (content, gen_id))
        self.conn.commit()

    def replace_fact_flags(self, gen_id: int, flags: list[dict]) -> None:
        self.conn.execute("DELETE FROM fact_flags WHERE generation_id=?", (gen_id,))
        for f in flags:
            self.conn.execute(
                "INSERT INTO fact_flags (generation_id, claim, verdict, source_snippet)"
                " VALUES (?,?,?,?)",
                (gen_id, f["claim"], f["verdict"], f.get("source_snippet", "")))
        self.conn.commit()

    def open_flags(self, story_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT ff.* FROM fact_flags ff JOIN generations g ON g.id = ff.generation_id
               WHERE g.story_id=? AND ff.status='open' ORDER BY ff.id""",
            (story_id,)).fetchall()
        return [dict(r) for r in rows]

    def resolve_flag(self, flag_id: int, resolution: str) -> None:
        self.conn.execute("UPDATE fact_flags SET status=? WHERE id=?", (resolution, flag_id))
        self.conn.commit()

    def create_publication(self, story_id: int, destination: str, url: str | None,
                           commit_sha: str | None, detail: str | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO publications (story_id, destination, url, commit_sha, detail)"
            " VALUES (?,?,?,?,?)", (story_id, destination, url, commit_sha, detail))
        self.conn.commit()
        return cur.lastrowid

    def list_publications(self) -> list[dict]:
        rows = self.conn.execute(
            """SELECT p.*, s.title FROM publications p
               JOIN stories s ON s.id = p.story_id ORDER BY p.id DESC""").fetchall()
        return [dict(r) for r in rows]

    def set_story_status(self, story_id: int, status: str) -> None:
        self.conn.execute("UPDATE stories SET status=?, updated_at=? WHERE id=?",
                          (status, datetime.now(timezone.utc).isoformat(), story_id))
        self.conn.commit()

    def get_story(self, story_id: int) -> StoryRecord | None:
        r = self.conn.execute("SELECT * FROM stories WHERE id=?", (story_id,)).fetchone()
        return self._row_to_story(r) if r else None

    def all_source_names(self) -> list[str]:
        return [r["name"] for r in
                self.conn.execute("SELECT name FROM sources ORDER BY name").fetchall()]
```

Add `timezone` to the `from datetime import ...` line in `db.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_db_publications.py tests/test_db.py -v`
Expected: PASSED (new file 3 + Plan 1 db tests still green).

- [ ] **Step 5: Commit**

```bash
git add sparks/db.py tests/test_db_publications.py
git commit -m "feat: generations, fact flags, publications tables"
```

---

### Task 3: Story/surface API routes + background job runner

**Files:**
- Create: `sparks/server/jobs.py`, `sparks/server/routes.py`
- Modify: `sparks/server/app.py` (include router), `sparks/context.py` (new — move `story_context` out of JudgeService), `sparks/judge/service.py` (use `sparks.context`)
- Test: `tests/test_server_jobs.py`, `tests/test_server_routes.py`

**Interfaces:**
- Consumes: Tasks 1–2 + Plan 1 (`run_cycle`, `queue_stories`, `story_members`, `latest_judge`).
- Produces:
  - `JobRunner.submit(name: str, fn, *args) -> str`, `.status(job_id) -> dict` (`{"name", "state": "running|done|error", "result"?, "error"?}`)
  - Routes: `GET /api/queue?band=&n=`, `GET /api/stories/{id}`, `POST /api/stories/{id}/select`, `GET /api/sources`, `POST /api/fetch-now` `-> {"job_id"}`, `GET /api/jobs/{job_id}`
  - `sparks.context.story_context(db, story) -> StoryContext` (same behavior as JudgeService._context_for)

- [ ] **Step 1: Write the failing tests**

`tests/test_server_jobs.py`:

```python
import time

from sparks.server.jobs import JobRunner


def test_job_runs_and_reports_done():
    runner = JobRunner()
    job_id = runner.submit("double", lambda x: x * 2, 21)
    for _ in range(100):
        if runner.status(job_id)["state"] != "running":
            break
        time.sleep(0.02)
    assert runner.status(job_id) == {"name": "double", "state": "done", "result": 42}


def test_job_error_captured():
    runner = JobRunner()
    job_id = runner.submit("boom", lambda: 1 / 0)
    for _ in range(100):
        if runner.status(job_id)["state"] != "running":
            break
        time.sleep(0.02)
    status = runner.status(job_id)
    assert status["state"] == "error" and "ZeroDivisionError" in status["error"]
```

`tests/test_server_routes.py`:

```python
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.models import FetchedEntry, Source
from sparks.server.app import create_app

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


@pytest.fixture
def env(settings):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss",
                                  credibility=0.8))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    story_id = db.create_story("Jeddah expansion", iid)
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, 88.0, "high", "ports-shipping")
    app = create_app(settings, db=db)
    tc = TestClient(app)
    headers = {"X-Sparks-Token": db.get_setting("server_token")}
    return tc, headers, db, story_id


def test_queue_endpoint(env):
    tc, h, db, story_id = env
    r = tc.get("/api/queue", headers=h)
    assert r.status_code == 200
    data = r.json()["stories"]
    assert data[0]["title"] == "Jeddah expansion"
    assert data[0]["priority"] == 88.0 and data[0]["n_sources"] == 1
    assert "rationale" in data[0]["judge"]  # explainability payload


def test_story_detail_includes_local_only_sources(env):
    tc, h, db, story_id = env
    r = tc.get(f"/api/stories/{story_id}", headers=h)
    assert r.status_code == 200
    detail = r.json()
    assert detail["sources"][0]["name"] == "Reuters"
    assert detail["sources"][0]["local_only"] is True
    assert detail["story"]["status"] == "ranked"


def test_select_and_fetch_now(env, monkeypatch):
    tc, h, db, story_id = env
    assert tc.post(f"/api/stories/{story_id}/select", headers=h).status_code == 200
    assert db.get_story(story_id).status == "selected"

    import sparks.server.routes as routes
    monkeypatch.setattr(routes, "run_cycle",
                        lambda s: type("R", (), {"errors": [], "items_new": 1,
                                                 "stories_created": 0,
                                                 "stories_judged": 0,
                                                 "stories_ranked": 0})())
    r = tc.post("/api/fetch-now", headers=h)
    job_id = r.json()["job_id"]
    for _ in range(100):
        if tc.get(f"/api/jobs/{job_id}", headers=h).json()["state"] != "running":
            break
    assert tc.get(f"/api/jobs/{job_id}", headers=h).json()["state"] == "done"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_server_jobs.py tests/test_server_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.server.jobs'`.

- [ ] **Step 3: Implement `sparks/context.py` and refactor `JudgeService`**

`sparks/context.py`:

```python
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
```

In `sparks/judge/service.py`: delete `_SENTENCE_RE` and `_context_for`, replace the body's use with `from sparks.context import story_context` and `ctx = story_context(self.db, pending[0])`. Re-run Plan 1's `tests/test_judge_service.py` — must stay green.

- [ ] **Step 4: Implement `sparks/server/jobs.py`**

```python
"""Tiny background job registry on a ThreadPoolExecutor."""
from __future__ import annotations

import concurrent.futures
import threading


class JobRunner:
    def __init__(self, workers: int = 2):
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
        self._jobs: dict[str, dict] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn, *args) -> str:
        import uuid
        job_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._jobs[job_id] = {"name": name, "state": "running"}
        future = self._pool.submit(fn, *args)
        future.add_done_callback(lambda f: self._finish(job_id, f))
        return job_id

    def _finish(self, job_id: str, future) -> None:
        with self._lock:
            if future.exception():
                self._jobs[job_id] = {"name": self._jobs[job_id]["name"], "state": "error",
                                      "error": f"{type(future.exception()).__name__}: "
                                               f"{future.exception()}"}
            else:
                self._jobs[job_id] = {"name": self._jobs[job_id]["name"], "state": "done",
                                      "result": future.result()}

    def status(self, job_id: str) -> dict:
        with self._lock:
            return dict(self._jobs.get(job_id, {"name": "?", "state": "unknown"}))
```

- [ ] **Step 5: Implement `sparks/server/routes.py` and wire into `app.py`**

```python
"""API routes for the dashboard."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from sparks.models import CycleReport
from sparks.pipeline import run_cycle

router = APIRouter(prefix="/api")


def _db(request: Request):
    return request.app.state.db


def _settings(request: Request):
    return request.app.state.settings


@router.get("/queue")
def queue(request: Request, band: str | None = None, n: int = 50):
    db = _db(request)
    stories = db.queue_stories(limit=n, band=band)
    out = []
    for s in stories:
        judge = db.latest_judge(s.id)
        out.append({
            "id": s.id, "title": s.title, "priority": s.priority, "band": s.band,
            "category": s.category, "status": s.status, "n_sources": s.n_sources,
            "judge": {"gist": judge.gist, "category": judge.suggested_category,
                      "rationale": judge.rationale_market_impact,
                      "scores": {"sc": judge.supply_chain_relevance,
                                 "saudi": judge.saudi_gcc_relevance,
                                 "impact": judge.market_impact,
                                 "novelty": judge.novelty}} if judge else None,
        })
    return {"stories": out}


@router.get("/stories/{story_id}")
def story_detail(request: Request, story_id: int):
    db = _db(request)
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "story not found")
    sources = [{"name": db.get_source(m.source_id).name,
                "url": m.url,  # LOCAL-ONLY: shown in dashboard, never published
                "local_only": True}
               for m in db.story_members(story_id)]
    judge = db.latest_judge(story_id)
    return {"story": {"id": story.id, "title": story.title, "status": story.status,
                      "priority": story.priority, "band": story.band,
                      "category": story.category, "judge_status": story.judge_status},
            "sources": sources,
            "judge": judge.__dict__ if judge else None,
            "generations": db.generations_for(story_id),
            "open_flags": db.open_flags(story_id)}


@router.post("/stories/{story_id}/select")
def select_story(request: Request, story_id: int):
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    db.set_story_status(story_id, "selected")
    return {"status": "selected"}


@router.get("/sources")
def sources(request: Request):
    return {"sources": [{"name": s.name, "kind": s.kind, "url": s.url,
                         "healthy": s.healthy, "enabled": s.enabled,
                         "credibility": s.credibility}
                        for s in _db(request).all_sources(enabled_only=False)]}


@router.post("/fetch-now")
def fetch_now(request: Request):
    settings = _settings(request)
    runner = request.app.state.job_runner
    job_id = runner.submit("fetch", run_cycle, settings)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(request: Request, job_id: str):
    return request.app.state.job_runner.status(job_id)
```

In `create_app`: accept `job_runner=None` (default `JobRunner()`), store on `app.state.job_runner`, and `app.include_router(router)`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_server_jobs.py tests/test_server_routes.py tests/test_judge_service.py -v`
Expected: all PASSED.

- [ ] **Step 7: Commit**

```bash
git add sparks/context.py sparks/judge/service.py sparks/server/ tests/test_server_jobs.py tests/test_server_routes.py
git commit -m "feat: story api routes and background job runner"
```

---

### Task 4: Generation prompts, output models, publishability validator

**Files:**
- Modify: `sparks/judge/api.py` (rename `_parse_content` → `parse_json_content`, keep a `_parse_content = parse_json_content` alias so Plan 1 tests stay green)
- Create: `sparks/generate/__init__.py` (empty), `sparks/generate/schema.py`, `sparks/generate/prompt.py`, `sparks/generate/validate.py`, `sparks/prompts/article_en_v1.md`, `sparks/prompts/article_ar_v1.md`, `sparks/prompts/linkedin_en_v1.md`, `sparks/prompts/linkedin_ar_v1.md`
- Test: `tests/test_generate_schema.py`, `tests/test_generate_prompt.py`, `tests/test_generate_validate.py`

**Interfaces:**
- Consumes: `StoryContext` (Plan 1), `parse_json_content`.
- Produces:
  - `GeneratedArticle` (pydantic: `headline, summary, what_happened, why_it_matters, takeaways: list[str]`) with `.to_markdown() -> str`
  - `LinkedInPost` (pydantic: `hook, insights: list[str], cta, hashtags: list[str]`) with `.to_text() -> str` (≤1300 visible chars before "see more" target)
  - `SeoBlock` (pydantic: `slug, description, tags: list[str]`)
  - `render_generation_prompt(kind: str, language: str, ctx: StoryContext, settings=None) -> list[dict]` (kind ∈ `article|linkedin`)
  - `assert_publishable(text: str, blocked_names: list[str]) -> list[str]` — returns violation strings; empty list = publishable

- [ ] **Step 1: Write the failing tests**

`tests/test_generate_schema.py`:

```python
import pytest
from pydantic import ValidationError

from sparks.generate.schema import GeneratedArticle, LinkedInPost, SeoBlock


def test_article_to_markdown():
    art = GeneratedArticle(headline="Jeddah capacity push", summary="Two million TEU added.",
                           what_happened="Works begin this quarter.",
                           why_it_matters="Strengthens the western corridor.",
                           takeaways=["Capacity: +2m TEU", "Timeline: 18 months"])
    md = art.to_markdown()
    assert md.startswith("Jeddah capacity push") and "## " in md
    assert "- Capacity: +2m TEU" in md
    assert "http" not in md


def test_linkedin_to_text_shape():
    post = LinkedInPost(hook="Big port news.", insights=["One.", "Two."],
                        cta="What does this mean for regional transshipment?",
                        hashtags=["supplychain", "saudiarabia"])
    text = post.to_text()
    assert text.split("\n\n")[0] == "Big port news."
    assert text.rstrip().endswith("#supplychain #saudiarabia")
    assert len(text) <= 1300


def test_missing_fields_rejected():
    with pytest.raises(ValidationError):
        LinkedInPost(hook="only hook")
```

`tests/test_generate_prompt.py`:

```python
from sparks.generate.prompt import render_generation_prompt
from sparks.judge.schema import StoryContext


def test_article_en_prompt_has_constraints_and_context():
    ctx = StoryContext(title="Jeddah expansion", lead="Mawani announced works.",
                       body="Body.", n_sources=3)
    msgs = render_generation_prompt("article", "en", ctx)
    system = msgs[0]["content"]
    assert "Do NOT mention any publisher" in system
    assert "URLs" in system and "invent" in system.lower()
    assert "Jeddah expansion" in msgs[1]["content"]


def test_linkedin_ar_prompt_exists_and_mentions_arabic():
    msgs = render_generation_prompt("linkedin", "ar",
                                    StoryContext("t", "l", "b", 1))
    assert "Arabic" in msgs[0]["content"] or "Arabic" in msgs[1]["content"]
```

`tests/test_generate_validate.py`:

```python
from sparks.generate.validate import assert_publishable


def test_clean_text_passes():
    assert assert_publishable("Plain analysis text.", ["Reuters"]) == []


def test_urls_flagged():
    violations = assert_publishable("See https://example.com and www.news.com", [])
    assert len(violations) == 2


def test_blocked_source_names_flagged_case_insensitive():
    violations = assert_publishable("As reported by REUTERS today.", ["Reuters"])
    assert violations and "Reuters" in violations[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_schema.py tests/test_generate_prompt.py tests/test_generate_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.generate'`.

- [ ] **Step 3: Implement `sparks/generate/schema.py`**

```python
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
```

- [ ] **Step 4: Create the four prompt templates**

`sparks/prompts/article_en_v1.md`:

```markdown
# Article Prompt — article_en_v1

## SYSTEM

You are a senior supply chain journalist writing for Supply Chain Sparks, a
publication covering supply chain developments in Saudi Arabia and the GCC.

HARD CONSTRAINTS:
- Do NOT mention any publisher, outlet, or source name.
- Do NOT include any URLs or links.
- Do NOT invent numbers, dates, company names, or statistics. Use only facts
  present in the material below.

Write a publication-ready article in English with exactly these JSON fields:
headline (string), summary (2 sentences), what_happened (2-3 short paragraphs),
why_it_matters (1-2 paragraphs focused on Saudi/GCC supply chain impact),
takeaways (3-5 bullet strings, each starting with a "Label:" prefix).

Return ONLY the JSON object.

## USER

Story title: {{TITLE}}

Editor gist: {{GIST}}

Material:
{{LEAD}}

{{BODY}}

Corroborated by {{N_SOURCES}} independent sources.
```

`sparks/prompts/article_ar_v1.md` — identical structure, SYSTEM in English with the instruction: "Write in native, professional journalistic Arabic (not a literal translation). Keep company names and port names in their standard Arabic business usage; numbers in Western Arabic numerals." Same JSON keys (values in Arabic). Same HARD CONSTRAINTS block verbatim.

`sparks/prompts/linkedin_en_v1.md`:

```markdown
# LinkedIn Prompt — linkedin_en_v1

## SYSTEM

You write LinkedIn posts for Supply Chain Sparks (supply chain intelligence,
Saudi Arabia / GCC). Tone: sharp, professional, insight-first.

HARD CONSTRAINTS:
- Do NOT mention any publisher, outlet, or source name.
- Do NOT include any URLs or links.
- Do NOT invent numbers, dates, company names, or statistics.

Structure the post so the FIRST line works as a hook before the "...see more"
fold. Total length under 1200 characters. JSON fields: hook (one line),
insights (3-5 strings, each one line), cta (one question), hashtags
(3-5 strings without the # character).

Return ONLY the JSON object.

## USER

Story title: {{TITLE}}

Editor gist: {{GIST}}

Material:
{{LEAD}}

{{BODY}}
```

`sparks/prompts/linkedin_ar_v1.md` — same, with the Arabic-native instruction from `article_ar_v1.md`.

- [ ] **Step 5: Implement `sparks/generate/prompt.py` and `validate.py`**

```python
"""Render generation prompts from versioned templates."""
from __future__ import annotations

import importlib.resources
import pathlib

from sparks.config import Settings
from sparks.judge.schema import StoryContext

_KINDS = {("article", "en"): "article_en_v1", ("article", "ar"): "article_ar_v1",
          ("linkedin", "en"): "linkedin_en_v1", ("linkedin", "ar"): "linkedin_ar_v1"}


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
```

```python
"""Mechanical publishability check: no links, no source names."""
from __future__ import annotations

import re

_URL_RE = re.compile(r"(https?://\S+|\bwww\.\S+)")


def assert_publishable(text: str, blocked_names: list[str]) -> list[str]:
    violations: list[str] = []
    violations += [f"contains URL: {m}" for m in _URL_RE.findall(text)]
    lowered = text.lower()
    for name in blocked_names:
        if name and name.lower() in lowered:
            violations.append(f"mentions source name: {name}")
    return violations
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate_schema.py tests/test_generate_prompt.py tests/test_generate_validate.py tests/test_judge_clients.py -v`
Expected: all PASSED (judge tests confirm the `parse_json_content` rename didn't break anything).

- [ ] **Step 7: Commit**

```bash
git add sparks/generate/ sparks/prompts/ sparks/judge/api.py tests/
git commit -m "feat: generation prompts, output models, publishability validator"
```

---

### Task 5: Generation service + endpoints

**Files:**
- Create: `sparks/generate/service.py`
- Modify: `sparks/server/routes.py` (generate endpoint)
- Test: `tests/test_generate_service.py`

**Interfaces:**
- Consumes: `story_context`, `parse_json_content`, prompt renderer, DB methods (Task 2), settings `judge.api` (the API writer tier — same base_url/key/model as the judge).
- Produces: `GenerationService(settings, db, api_client: httpx.Client | None = None)` with `.generate_for_story(story_id: int, formats: tuple[str, ...] = ("article", "linkedin")) -> list[int]`; route `POST /api/stories/{id}/generate` `{"formats": [...]}` → `{"job_id"}`; story status moves `selected|ranked → generating → review`.

- [ ] **Step 1: Write the failing tests**

`tests/test_generate_service.py`:

```python
import json
from datetime import datetime, timezone

import pytest
import respx

from sparks.db import Database
from sparks.generate.service import GenerationService
from sparks.models import FetchedEntry, JudgeOutput, Source

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)

ARTICLE = {"headline": "Jeddah pushes capacity", "summary": "Major works ahead.",
           "what_happened": "Works begin.", "why_it_matters": "Regional hub effect.",
           "takeaways": ["Capacity: up", "Timeline: fast"]}
LINKEDIN = {"hook": "Big port news.", "insights": ["One."], "cta": "Thoughts?",
            "hashtags": ["supplychain"]}
SEO = {"slug": "jeddah-capacity", "description": "desc", "tags": ["ports"]}


def _reply(payload):
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@pytest.fixture
def seeded(settings):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    db.update_item_extraction(iid, "First sentence. Second. " + "word " * 200,
                              None, 205)
    story_id = db.create_story("Jeddah expansion", iid)
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, 88.0, "high", "ports-shipping")
    return db, story_id


@respx.mock
def test_generates_all_four_formats_and_seo(seeded, settings):
    db, story_id = seeded
    route = respx.post("https://api.example/v4/chat/completions")
    route.side_effect = [_reply(ARTICLE), _reply(SEO), _reply(ARTICLE), _reply(SEO),
                         _reply(LINKEDIN), _reply(LINKEDIN)]
    # order: article-en, seo-en, article-ar, seo-ar, linkedin-en, linkedin-ar
    gen_ids = GenerationService(settings, db).generate_for_story(story_id)
    assert len(gen_ids) == 6
    gens = db.generations_for(story_id)
    assert {(g["format"], g["language"]) for g in gens} == {
        ("article", "en"), ("article", "ar"), ("linkedin", "en"), ("linkedin", "ar")}
    assert db.get_story(story_id).status == "review"
    assert "## What happened" in gens[0]["content"]


@respx.mock
def test_generation_blocks_unpublishable_content(seeded, settings):
    db, story_id = seeded
    bad = dict(ARTICLE, what_happened="Read more at https://example.com")
    respx.post("https://api.example/v4/chat/completions").respond(json=_reply(bad))
    with pytest.raises(Exception) as exc:
        GenerationService(settings, db).generate_for_story(story_id, formats=("article",))
    assert "URL" in str(exc.value) or "publishable" in str(exc.value)
    assert db.generations_for(story_id) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_generate_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.generate.service'`.

- [ ] **Step 3: Implement `sparks/generate/service.py`**

```python
"""GenerationService: story -> article/linkedin content in EN + AR."""
from __future__ import annotations

import httpx

from sparks.config import Settings
from sparks.context import story_context
from sparks.db import Database
from sparks.generate.prompt import render_generation_prompt
from sparks.generate.schema import GeneratedArticle, LinkedInPost, SeoBlock
from sparks.generate.validate import assert_publishable
from sparks.judge.api import parse_json_content
from sparks.models import StoryRecord


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
        ctx.body = (f"Gist: {judge.gist}\n\n{ctx.body}" if judge else ctx.body)
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


import json  # noqa: E402  (used by seo_tags serialization above)
```

(The `import json` belongs at the top of the file — place it with the other imports.)

**SEO prompt:** the service references `("seo", language)` — add `sparks/prompts/seo_en_v1.md` and `sparks/prompts/ar` variant mapping `("seo", "en") -> seo_en_v1`, `("seo", "ar") -> seo_ar_v1` to `_KINDS` in `prompt.py`. `seo_en_v1.md` SYSTEM: "From the article material, produce JSON: slug (kebab-case, english, max 60 chars), description (max 155 chars), tags (3-6 kebab-case strings)." Same HARD CONSTRAINTS block. AR variant: slug still English kebab-case; description/tags in Arabic.

Update the `_KINDS` dict accordingly:

```python
_KINDS = {("article", "en"): "article_en_v1", ("article", "ar"): "article_ar_v1",
          ("linkedin", "en"): "linkedin_en_v1", ("linkedin", "ar"): "linkedin_ar_v1",
          ("seo", "en"): "seo_en_v1", ("seo", "ar"): "seo_ar_v1"}
```

**Route** (append to `routes.py`):

```python
@router.post("/stories/{story_id}/generate")
def generate(request: Request, story_id: int, body: dict = {"formats": ["article", "linkedin"]}):
    from sparks.generate.service import GenerationService
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    service = GenerationService(_settings(request), db)
    formats = tuple(body.get("formats", ["article", "linkedin"]))
    job_id = request.app.state.job_runner.submit("generate", service.generate_for_story,
                                                 story_id, formats)
    return {"job_id": job_id}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_generate_service.py -v`
Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/generate/ sparks/prompts/ sparks/server/routes.py tests/test_generate_service.py
git commit -m "feat: bilingual generation service with publishability gate"
```

---

### Task 6: Fact-check service + approval gating

**Files:**
- Create: `sparks/factcheck/__init__.py` (empty), `sparks/factcheck/service.py`, `sparks/prompts/factcheck_v1.md`
- Modify: `sparks/server/routes.py` (fact-check, resolve-flag, approve endpoints)
- Test: `tests/test_factcheck.py`

**Interfaces:**
- Consumes: `generations`/`fact_flags` tables (Task 2), `story_members` extracted texts, API tier.
- Produces: `FactCheckService(settings, db, api_client=None).check_generation(generation_id) -> int` (number of open flags); routes `POST /api/generations/{id}/fact-check` → `{"job_id"}`, `POST /api/flags/{id}/resolve` `{"resolution": "resolved_edit|resolved_confirm"}`, `POST /api/stories/{id}/approve` → 200 or **409** with `{"detail": "open flags"}` / `{"detail": "no generations"}`; approve sets status `approved`.

- [ ] **Step 1: Create `sparks/prompts/factcheck_v1.md`**

```markdown
# Fact-check Prompt — factcheck_v1

## SYSTEM

You are a meticulous fact checker for a supply chain publication. You receive a
draft (generated article or post) and the source material it was based on.

For EVERY factual claim in the draft (numbers, dates, capacities, company names,
locations, policy facts), verify it appears in the source material.

Return ONLY JSON: {"claims": [{"claim": "...", "verdict": "supported" |
"unsupported" | "unverifiable", "source_snippet": "..."}]}

- "supported": the claim maps to a specific passage; quote it in source_snippet.
- "unsupported": the material contradicts it or lacks it while it is checkable.
- "unverifiable": vague or opinion framing that cannot be checked factually.

Do not evaluate style, only facts.

## USER

DRAFT:
{{DRAFT}}

SOURCE MATERIAL:
{{SOURCES}}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_factcheck.py`:

```python
import json
from datetime import datetime, timezone

import pytest
import respx
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.factcheck.service import FactCheckService
from sparks.models import FetchedEntry, Source
from sparks.server.app import create_app

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)

CLAIMS = {"claims": [
    {"claim": "adds two million TEU", "verdict": "supported",
     "source_snippet": "expand container capacity by two million TEU"},
    {"claim": "completion by 2031", "verdict": "unsupported", "source_snippet": ""},
    {"claim": "positions the kingdom well", "verdict": "unverifiable",
     "source_snippet": ""},
]}


@pytest.fixture
def seeded(settings):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Story", NOW), "raw", NOW)
    db.update_item_extraction(iid, "expand container capacity by two million TEU.",
                              None, 10)
    story_id = db.create_story("Story", iid)
    gen_id = db.save_generation(story_id=story_id, format="article", language="en",
                                model="m", prompt_version="article_en_v1",
                                content="adds two million TEU, completion by 2031, "
                                        "positions the kingdom well")
    app = create_app(settings, db=db)
    tc = TestClient(app)
    return tc, {"X-Sparks-Token": db.get_setting("server_token")}, db, story_id, gen_id


@respx.mock
def test_check_generation_stores_flags(seeded, settings):
    tc, h, db, story_id, gen_id = seeded
    respx.post("https://api.example/v4/chat/completions").respond(
        200, json={"choices": [{"message": {"content": json.dumps(CLAIMS)}}]})
    flags = FactCheckService(settings, db).check_generation(gen_id)
    assert flags == 2  # unsupported + unverifiable
    assert len(db.open_flags(story_id)) == 2


def test_approve_blocked_until_flags_resolved(seeded):
    tc, h, db, story_id, gen_id = seeded
    db.replace_fact_flags(gen_id, [{"claim": "c", "verdict": "unsupported",
                                    "source_snippet": ""}])
    r = tc.post(f"/api/stories/{story_id}/approve", headers=h)
    assert r.status_code == 409
    flag_id = db.open_flags(story_id)[0]["id"]
    r = tc.post(f"/api/flags/{flag_id}/resolve", headers=h,
                json={"resolution": "resolved_confirm"})
    assert r.status_code == 200
    r = tc.post(f"/api/stories/{story_id}/approve", headers=h)
    assert r.status_code == 200 and db.get_story(story_id).status == "approved"


def test_approve_requires_generations(seeded):
    tc, h, db, story_id, gen_id = seeded
    db.conn.execute("DELETE FROM generations")
    db.conn.commit()
    assert tc.post(f"/api/stories/{story_id}/approve", headers=h).status_code == 409
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_factcheck.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.factcheck'`.

- [ ] **Step 4: Implement `sparks/factcheck/service.py`**

```python
"""FactCheckService: verify generated claims against source material."""
from __future__ import annotations

import httpx

from sparks.config import Settings
from sparks.db import Database
from sparks.judge.api import parse_json_content
from pydantic import BaseModel, field_validator


class ClaimList(BaseModel):
    claims: list[dict]

    @field_validator("claims")
    @classmethod
    def _non_empty(cls, v):
        if not isinstance(v, list):
            raise ValueError("claims must be a list")
        return v


class FactCheckService:
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

    def check_generation(self, generation_id: int) -> int:
        gen = self._generation(generation_id)
        story = self.db.get_story(gen["story_id"])
        sources = "\n---\n".join(
            (m.extracted_text or "")[:2000] for m in self.db.story_members(story.id))
        prompt = self._render(gen["content"], sources)
        cfg = self.settings.judge.api
        resp = self.client.post(
            f"{cfg.base_url.rstrip('/')}/chat/completions",
            json={"model": cfg.model, "messages": prompt, "temperature": 0.0},
            headers={"authorization": f"Bearer {cfg.api_key}"})
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        claims = parse_json_content(content, ClaimList).claims
        flags = [c for c in claims if c.get("verdict") != "supported"]
        self.db.replace_fact_flags(generation_id, claims)
        return len(flags)

    def _generation(self, generation_id: int) -> dict:
        row = self.db.conn.execute("SELECT * FROM generations WHERE id=?",
                                   (generation_id,)).fetchone()
        if not row:
            raise ValueError(f"generation {generation_id} not found")
        return dict(row)

    def _render(self, draft: str, sources: str) -> list[dict]:
        import importlib.resources
        template = (importlib.resources.files("sparks") / "prompts" / "factcheck_v1.md"
                    ).read_text(encoding="utf-8")
        system_part, _, user_part = template.partition("## USER")
        system = system_part.split("## SYSTEM", 1)[-1].strip()
        user = user_part.strip().replace("{{DRAFT}}", draft).replace("{{SOURCES}}", sources)
        return [{"role": "system", "content": system},
                {"role": "user", "content": user}]
```

**Routes** (append to `routes.py`):

```python
@router.post("/generations/{generation_id}/fact-check")
def fact_check(request: Request, generation_id: int):
    from sparks.factcheck.service import FactCheckService
    service = FactCheckService(_settings(request), _db(request))
    job_id = request.app.state.job_runner.submit("factcheck", service.check_generation,
                                                 generation_id)
    return {"job_id": job_id}


@router.post("/flags/{flag_id}/resolve")
def resolve_flag(request: Request, flag_id: int, body: dict):
    resolution = body.get("resolution")
    if resolution not in ("resolved_edit", "resolved_confirm"):
        raise HTTPException(400, "resolution must be resolved_edit|resolved_confirm")
    _db(request).resolve_flag(flag_id, resolution)
    return {"status": resolution}


@router.post("/stories/{story_id}/approve")
def approve(request: Request, story_id: int):
    db = _db(request)
    if not db.get_story(story_id):
        raise HTTPException(404, "story not found")
    if not db.generations_for(story_id):
        raise HTTPException(409, "no generations")
    if db.open_flags(story_id):
        raise HTTPException(409, "open flags")
    db.set_story_status(story_id, "approved")
    return {"status": "approved"}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_factcheck.py -v`
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add sparks/factcheck/ sparks/prompts/factcheck_v1.md sparks/server/routes.py tests/test_factcheck.py
git commit -m "feat: fact-check service gating approval"
```

---

### Task 7: Git publisher (dulwich)

**Files:**
- Create: `sparks/publish/__init__.py` (empty), `sparks/publish/git.py`
- Test: `tests/test_publish_git.py`

**Interfaces:**
- Consumes: `settings.publish` (`repo_url`, `branch`, `token`, `site_base_url`), data dir for the local clone.
- Produces: `GitPublisher(settings)`, `.publish(files: dict[str, str], message: str) -> str` (commit sha; keys are repo-relative paths like `content/posts/<slug>/en.md`), `.build_url(slug: str) -> str`; helper `authed_url(repo_url, token) -> str`.

- [ ] **Step 1: Write the failing tests**

`tests/test_publish_git.py`:

```python
import pytest
from dulwich import porcelain

from sparks.publish.git import GitPublisher, authed_url


def test_authed_url_embeds_token():
    assert (authed_url("https://github.com/org/repo.git", "tk") ==
            "https://x-access-token:tk@github.com/org/repo.git")
    assert authed_url("https://github.com/org/repo.git", "") == "https://github.com/org/repo.git"


@pytest.fixture
def repo_pair(settings, tmp_path):
    """Local bare 'remote' + publisher pointed at it."""
    settings.publish.repo_url = str(tmp_path / "remote.git")
    settings.publish.branch = "main"
    settings.publish.token = ""
    porcelain.init(str(tmp_path / "remote.git"), bare=True)
    return GitPublisher(settings), tmp_path / "remote.git"


def test_publish_writes_files_and_pushes(repo_pair):
    publisher, remote = repo_pair
    sha = publisher.publish({
        "content/posts/saudi-port-expansion-2026/en.md": "# hello",
        "content/posts/saudi-port-expansion-2026/meta.json": '{"slug": "x"}',
    }, "publish: test post")
    assert len(sha) == 40
    with porcelain.open_repo_closing(str(remote)) as repo:
        assert b"main" in repo.refs
        tree = repo[repo[repo.refs[b"refs/heads/main"]].tree]
        paths = {p.decode() for p, _, _ in repo.object_store.iter_tree(tree.id)}
    assert "content/posts/saudi-port-expansion-2026/en.md" in paths


def test_second_publish_adds_file(repo_pair):
    publisher, remote = repo_pair
    publisher.publish({"content/posts/a/en.md": "one"}, "first")
    publisher.publish({"content/posts/b/en.md": "two"}, "second")
    with porcelain.open_repo_closing(str(remote)) as repo:
        commit = repo[repo[repo.refs[b"refs/heads/main"]]]
        tree = repo[commit.tree]
        paths = {p.decode() for p, _, _ in repo.object_store.iter_tree(tree.id)}
    assert {"content/posts/a/en.md", "content/posts/b/en.md"} <= paths


def test_build_url(repo_pair):
    publisher, _ = repo_pair
    assert publisher.build_url("my-post") == "https://supplychainsparks.com/post/my-post"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_publish_git.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.publish'`.

- [ ] **Step 3: Implement `sparks/publish/git.py`**

```python
"""Git publisher: dulwich clone/commit/push of the content repo (no git binary)."""
from __future__ import annotations

import pathlib
from urllib.parse import urlsplit, urlunsplit

from dulwich import porcelain

from sparks.config import Settings


def authed_url(repo_url: str, token: str) -> str:
    if not token or not repo_url.startswith("http"):
        return repo_url
    parts = urlsplit(repo_url)
    netloc = f"x-access-token:{token}@{parts.netloc}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


class GitError(Exception):
    pass


class GitPublisher:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.clone_dir = settings.data_dir / "content-repo"

    def _ensure_clone(self) -> None:
        url = authed_url(self.settings.publish.repo_url, self.settings.publish.token)
        if not (self.clone_dir / ".git").exists():
            self.clone_dir.parent.mkdir(parents=True, exist_ok=True)
            porcelain.clone(url, str(self.clone_dir),
                            branch=self.settings.publish.branch.encode())
        else:
            porcelain.pull(str(self.clone_dir), url,
                           refspecs=f"refs/heads/{self.settings.publish.branch}".encode())

    def publish(self, files: dict[str, str], message: str) -> str:
        if not self.settings.publish.repo_url:
            raise GitError("publish.repo_url not configured")
        self._ensure_clone()
        for rel_path, content in files.items():
            path = self.clone_dir / pathlib.PurePosixPath(rel_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        with porcelain.open_repo_closing(str(self.clone_dir)) as repo:
            for rel_path in files:
                porcelain.add(repo=repo, paths=[str(self.clone_dir / rel_path)])
            sha = porcelain.commit(repo=repo, message=message.encode())
            remote = authed_url(self.settings.publish.repo_url,
                                self.settings.publish.token)
            porcelain.push(repo, remote,
                           refspecs=f"refs/heads/{self.settings.publish.branch}".encode())
        return sha.decode() if isinstance(sha, bytes) else str(sha)

    def build_url(self, slug: str) -> str:
        base = self.settings.publish.site_base_url.rstrip("/")
        return f"{base}/post/{slug}"
```

Note: `porcelain.pull` on a fresh clone of an *empty* remote raises on some dulwich versions — wrap `_ensure_clone`'s pull in `try/except` and treat failure as "already current" only when the remote has no refs yet; otherwise re-raise. The tests pass because the first `publish` clones, and the second finds `.git` and pulls a remote that exists.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_publish_git.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/publish/git.py tests/test_publish_git.py
git commit -m "feat: dulwich git publisher for content repo"
```

---

### Task 8: Content contract writer + publish endpoint

**Files:**
- Create: `sparks/publish/content.py`
- Modify: `sparks/server/routes.py` (publish + publications endpoints)
- Test: `tests/test_publish_content.py`

**Interfaces:**
- Consumes: `generations_for`, `create_publication`, `GitPublisher` (Task 7), content contract.
- Produces: `build_post_files(meta: dict, en_md: str, ar_md: str | None) -> dict[str, str]`; `slugify(title: str) -> str`; routes `POST /api/stories/{id}/publish` `{"destinations": ["site"]}` (requires `approved`; site → git publish + publication row + live URL; also accepts `"linkedin"` → publication row with `url=None, detail="copied"`), `GET /api/publications`, `POST /api/generations/{id}` (content edit, body `{"content": "..."}`), `POST /api/generations/{id}/copy` (marks a linkedin copy event).

- [ ] **Step 1: Write the failing tests**

`tests/test_publish_content.py`:

```python
import json
from datetime import datetime, timezone

import pytest
from dulwich import porcelain
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.models import FetchedEntry, Source
from sparks.publish.content import build_post_files, slugify
from sparks.server.app import create_app

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_slugify():
    assert slugify("Jeddah Port: New 2M TEU Terminal!") == "jeddah-port-new-2m-teu-terminal"
    assert slugify("  Multiple   spaces ") == "multiple-spaces"


def test_build_post_files_contract():
    meta = {"slug": "x", "title": "T", "titleAr": "ت", "description": "d",
            "descriptionAr": "د", "category": "ports-shipping", "tags": ["a"],
            "publishedAt": "2026-09-08T14:30:00Z", "priority": 88.0}
    files = build_post_files(meta, "EN body", "AR body")
    assert set(files.keys()) == {"content/posts/x/en.md", "content/posts/x/ar.md",
                                 "content/posts/x/meta.json"}
    parsed = json.loads(files["content/posts/x/meta.json"])
    assert parsed["slug"] == "x" and parsed["titleAr"] == "ت"
    assert files["content/posts/x/en.md"] == "EN body"


@pytest.fixture
def approved_story(settings, tmp_path):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    story_id = db.create_story("Jeddah expansion", iid)
    for language, body in (("en", "English body"), ("ar", "Arabic body")):
        db.save_generation(story_id=story_id, format="article", language=language,
                           model="m", prompt_version="p", content=body,
                           seo_slug="jeddah-expansion", seo_description="d",
                           seo_tags='["jeddah"]')
    db.set_story_status(story_id, "approved")
    settings.publish.repo_url = str(tmp_path / "remote.git")
    settings.publish.token = ""
    porcelain.init(settings.publish.repo_url, bare=True)
    app = create_app(settings, db=db)
    tc = TestClient(app)
    return tc, {"X-Sparks-Token": db.get_setting("server_token")}, db, story_id


def test_publish_site_flow(approved_story):
    tc, h, db, story_id = approved_story
    r = tc.post(f"/api/stories/{story_id}/publish", headers=h,
                json={"destinations": ["site"]})
    assert r.status_code == 200
    body = r.json()
    assert body["url"] == "https://supplychainsparks.com/post/jeddah-expansion"
    assert len(body["commit_sha"]) == 40
    assert db.get_story(story_id).status == "published"
    pubs = tc.get("/api/publications", headers=h).json()["publications"]
    assert pubs[0]["destination"] == "site" and pubs[0]["published_at"]


def test_publish_requires_approved(approved_story):
    tc, h, db, story_id = approved_story
    db.set_story_status(story_id, "review")
    r = tc.post(f"/api/stories/{story_id}/publish", headers=h,
                json={"destinations": ["site"]})
    assert r.status_code == 409


def test_linkedin_copy_records_publication(approved_story):
    tc, h, db, story_id = approved_story
    r = tc.post(f"/api/stories/{story_id}/publish", headers=h,
                json={"destinations": ["linkedin"]})
    assert r.status_code == 200
    pubs = tc.get("/api/publications", headers=h).json()["publications"]
    assert pubs[0]["destination"] == "linkedin" and pubs[0]["detail"] == "copied"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_publish_content.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.publish.content'`.

- [ ] **Step 3: Implement `sparks/publish/content.py`**

```python
"""Content-repo file writer implementing the shared contract (see Plan 3)."""
from __future__ import annotations

import json
import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(title: str) -> str:
    ascii_title = (unicodedata.normalize("NFKD", title)
                   .encode("ascii", "ignore").decode("ascii"))
    slug = _SLUG_RE.sub("-", ascii_title.lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug) or "story"


def build_post_files(meta: dict, en_md: str, ar_md: str | None) -> dict[str, str]:
    base = f"content/posts/{meta['slug']}"
    files = {f"{base}/en.md": en_md,
             f"{base}/meta.json": json.dumps(meta, ensure_ascii=False, indent=2) + "\n"}
    if ar_md:
        files[f"{base}/ar.md"] = ar_md
    return files
```

**Routes** (append to `routes.py`):

```python
@router.post("/generations/{generation_id}")
def edit_generation(request: Request, generation_id: int, body: dict):
    content = body.get("content")
    if content is None:
        raise HTTPException(400, "content required")
    _db(request).update_generation_content(generation_id, content)
    return {"status": "updated"}


@router.post("/stories/{story_id}/publish")
def publish(request: Request, story_id: int, body: dict):
    from sparks.publish.content import build_post_files, slugify
    from sparks.publish.git import GitPublisher
    db = _db(request)
    settings = _settings(request)
    story = db.get_story(story_id)
    if not story:
        raise HTTPException(404, "story not found")
    if story.status != "approved":
        raise HTTPException(409, f"story is {story.status}, must be approved")
    gens = {(g["format"], g["language"]): g for g in db.generations_for(story_id)}
    result = {"destinations": {}}
    destinations = body.get("destinations", ["site"])
    if "site" in destinations:
        en = gens.get(("article", "en"))
        ar = gens.get(("article", "ar"))
        if not en:
            raise HTTPException(409, "no english article to publish")
        slug = en["seo_slug"] or slugify(story.title)
        meta = {"slug": slug,
                "title": story.title,
                "titleAr": _first_line(ar["content"]) if ar else "",
                "description": en["seo_description"] or "",
                "descriptionAr": (ar["seo_description"] or "") if ar else "",
                "category": story.category or "other",
                "tags": json.loads(en["seo_tags"] or "[]"),
                "publishedAt": datetime.now(timezone.utc).isoformat(),
                "priority": story.priority}
        publisher = GitPublisher(settings)
        sha = publisher.publish(build_post_files(meta, en["content"],
                                                 ar["content"] if ar else None),
                                f"publish: {slug}")
        url = publisher.build_url(slug)
        db.create_publication(story_id, "site", url=url, commit_sha=sha, detail="en+ar")
        db.set_story_status(story_id, "published")
        result["destinations"]["site"] = {"url": url, "commit_sha": sha}
        result["url"] = url
        result["commit_sha"] = sha
    if "linkedin" in destinations:
        db.create_publication(story_id, "linkedin", url=None, commit_sha=None,
                              detail="copied")
        result["destinations"]["linkedin"] = {"status": "copied"}
    return result


def _first_line(text: str) -> str:
    return text.strip().split("\n", 1)[0]


@router.get("/publications")
def publications(request: Request):
    return {"publications": _db(request).list_publications()}
```

Add `from datetime import datetime, timezone` and `import json` to `routes.py` imports.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_publish_content.py -v`
Expected: 5 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/publish/content.py sparks/server/routes.py tests/test_publish_content.py
git commit -m "feat: site publishing flow and content contract writer"
```

---

### Task 9: Scheduler + desktop shell (tray, webview, single instance)

**Files:**
- Create: `sparks/app/__init__.py` (empty), `sparks/app/scheduler.py`, `sparks/app/tray.py`, `sparks/app/main.py`
- Test: `tests/test_app_scheduler.py`, `tests/test_app_lock.py`

**Interfaces:**
- Consumes: `run_cycle` (Plan 1), `create_app` (Task 1), `JobRunner` (Task 3).
- Produces: `FetchScheduler(settings, job_runner).start()/.shutdown()` (interval = `settings.fetch.schedule_hours`, 0 = disabled); `acquire_lock(data_dir) -> bool` + `release_lock(data_dir)` (single-instance); `run() -> int` — the `sparks-app` entry point (uvicorn thread + webview window + tray; manual smoke only).

- [ ] **Step 1: Write the failing tests**

`tests/test_app_scheduler.py`:

```python
from sparks.app.scheduler import FetchScheduler


class FakeBgScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, fn, **kwargs):
        self.jobs.append((fn, kwargs))

    def shutdown(self):
        pass


def test_start_registers_interval_job_and_runs_now(settings):
    settings.fetch.schedule_hours = 6
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert called == ["fetch"]  # immediate first run
    fn, kwargs = sched.scheduler.jobs[0]
    assert kwargs["hours"] == 6


def test_zero_hours_disables(settings):
    settings.fetch.schedule_hours = 0
    called = []
    runner = type("R", (), {"submit": lambda self, name, fn, *a: called.append(name)})()
    sched = FetchScheduler(settings, runner, background=FakeBgScheduler())
    sched.start()
    assert sched.scheduler.jobs == [] and called == []
```

`tests/test_app_lock.py`:

```python
from sparks.app.main import acquire_lock, release_lock


def test_lock_is_exclusive(settings):
    assert acquire_lock(settings.data_dir) is True
    assert acquire_lock(settings.data_dir) is False
    release_lock(settings.data_dir)
    assert acquire_lock(settings.data_dir) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_app_scheduler.py tests/test_app_lock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sparks.app'`.

- [ ] **Step 3: Implement `sparks/app/scheduler.py`, `tray.py`, `main.py`**

`sparks/app/scheduler.py`:

```python
"""Scheduled fetching via APScheduler (injectable background for tests)."""
from __future__ import annotations

from sparks.config import Settings
from sparks.pipeline import run_cycle


class FetchScheduler:
    def __init__(self, settings: Settings, job_runner, background=None):
        self.settings = settings
        self.job_runner = job_runner
        if background is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            background = BackgroundScheduler()
        self.scheduler = background

    def start(self) -> None:
        self.job_runner.submit("fetch", run_cycle, self.settings)  # immediate first run
        hours = self.settings.fetch.schedule_hours
        if hours and hours > 0:
            self.scheduler.add_job(
                lambda: self.job_runner.submit("fetch", run_cycle, self.settings),
                "interval", hours=hours, id="fetch-cycle")
            self.scheduler.start()

    def shutdown(self) -> None:
        try:
            self.scheduler.shutdown(wait=False)
        except Exception:
            pass
```

`sparks/app/tray.py`:

```python
"""System tray icon. Icon image generated with Pillow (no asset files)."""
from __future__ import annotations

from PIL import Image, ImageDraw


def _icon_image():
    img = Image.new("RGB", (64, 64), "#0f766e")
    draw = ImageDraw.Draw(img)
    draw.polygon([(32, 10), (52, 32), (32, 54), (12, 32)], fill="#fbbf24")
    return img


def build_tray(on_open, on_fetch, on_quit):
    import pystray
    menu = pystray.Menu(
        pystray.MenuItem("Open Dashboard", lambda *_: on_open(), default=True),
        pystray.MenuItem("Fetch Now", lambda *_: on_fetch()),
        pystray.MenuItem("Quit", lambda *_: on_quit()),
    )
    return pystray.Icon("SupplyChainSparks", _icon_image(), "Supply Chain Sparks", menu)
```

`sparks/app/main.py`:

```python
"""Desktop entry: single instance, API server thread, scheduler, tray + webview."""
from __future__ import annotations

import logging
import os
import threading
from logging.handlers import RotatingFileHandler

from sparks.config import load_settings


def acquire_lock(data_dir) -> bool:
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = data_dir / "app.lock"
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def release_lock(data_dir) -> None:
    lock_path = data_dir / "app.lock"
    if lock_path.exists():
        lock_path.unlink()


def _setup_logging(data_dir) -> None:
    logs = data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / "sparks.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO,
                        handlers=[handler, logging.StreamHandler()],
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")


def run() -> int:
    settings = load_settings()
    if not acquire_lock(settings.data_dir):
        return 0  # already running
    _setup_logging(settings.data_dir)
    logging.getLogger(__name__).info("starting SupplyChainSparks app")

    import uvicorn
    from sparks.pipeline import run_cycle
    from sparks.server.app import create_app
    from sparks.server.jobs import JobRunner
    from sparks.app.scheduler import FetchScheduler

    job_runner = JobRunner()
    app = create_app(settings, job_runner=job_runner)
    config = uvicorn.Config(app, host=settings.server.host, port=settings.server.port,
                            log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()

    FetchScheduler(settings, job_runner).start()

    from sparks.app.tray import build_tray
    token = app.state.db.get_setting("server_token")
    dashboard_url = (f"http://{settings.server.host}:{settings.server.port}"
                     f"/?token={token}")

    tray = build_tray(
        on_open=lambda: _open_window(dashboard_url),
        on_fetch=lambda: job_runner.submit("fetch", run_cycle, settings),
        on_quit=lambda: _quit(server, tray, settings.data_dir),
    )

    _open_window(dashboard_url)   # main window at startup
    tray.run()                    # blocks until quit
    return 0


def _quit(server, tray, data_dir) -> None:
    server.should_exit = True
    tray.stop()
    release_lock(data_dir)
    os._exit(0)


def _open_window(url: str) -> None:
    import webview
    webview.create_window("Supply Chain Sparks", url, width=1280, height=800,
                          on_top=False)
    if not webview.windows or not any(w.visible for w in webview.windows):
        threading.Thread(target=webview.start, daemon=True).start()
```

(`webview.start()` may only be called once per process; opening later windows uses `webview.create_window` on the running loop — verify behavior manually in Task 12's smoke test and simplify to a single window + tray reopen if multi-window misbehaves.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_app_scheduler.py tests/test_app_lock.py -v`
Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add sparks/app/ tests/test_app_scheduler.py tests/test_app_lock.py
git commit -m "feat: scheduler, tray, single-instance desktop shell"
```

---

### Task 10: Frontend scaffold + app shell + Queue view

**Files:**
- Create: `dashboard/package.json`, `dashboard/vite.config.js`, `dashboard/index.html`, `dashboard/src/main.jsx`, `dashboard/src/App.jsx`, `dashboard/src/api.js`, `dashboard/src/styles.css`, `dashboard/src/views/QueueView.jsx`, `dashboard/src/views/__tests__/QueueView.test.jsx`, `dashboard/src/test/setup.js`, `dashboard/vitest.config.js`
- Test: `dashboard/src/views/__tests__/QueueView.test.jsx`

**Interfaces:**
- Consumes: Task 3 API (`GET /api/queue`, `POST /api/stories/{id}/select`).
- Produces: `api.js` — `setToken(t)`, `apiGet(path)`, `apiPost(path, body)`; `QueueView` — ranked cards with band badge, priority, judge rationale, generate/select actions; `App` — tab shell (Queue, Review, Published, Settings) + status footer.

- [ ] **Step 1: Scaffold files**

`dashboard/package.json`:

```json
{
  "name": "sparks-dashboard",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "jsdom": "^24.0.0"
  }
}
```

`dashboard/vite.config.js`:

```js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  build: { outDir: "dist" },
});
```

`dashboard/vitest.config.js`:

```js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.js"],
  },
});
```

`dashboard/src/test/setup.js`:

```js
import "@testing-library/jest-dom/vitest";
```

`dashboard/src/api.js`:

```js
let token = new URLSearchParams(location.search).get("token") || "";

export function setToken(t) { token = t; }
export function getToken() { return token; }

export async function apiGet(path) {
  const r = await fetch(path, { headers: { "X-Sparks-Token": token } });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

export async function apiPost(path, body = {}) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "X-Sparks-Token": token, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
```

`dashboard/src/main.jsx`:

```jsx
import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(<App />);
```

`dashboard/index.html`:

```html
<!doctype html>
<html lang="en">
  <head><meta charset="UTF-8" /><title>Supply Chain Sparks</title></head>
  <body><div id="root"></div><script type="module" src="/src/main.jsx"></script></body>
</html>
```

- [ ] **Step 2: Write the failing test**

`dashboard/src/views/__tests__/QueueView.test.jsx`:

```jsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect } from "vitest";
import QueueView from "../QueueView.jsx";

vi.mock("../../api.js", () => ({
  apiGet: vi.fn(async () => ({
    stories: [{
      id: 7, title: "Jeddah expansion", priority: 88, band: "high",
      category: "ports-shipping", n_sources: 3, status: "ranked",
      judge: { gist: "Big capex.", rationale: "Largest this year.",
               scores: { sc: 9, saudi: 10, impact: 8, novelty: 7 } },
    }],
  })),
  apiPost: vi.fn(async () => ({ status: "selected" })),
}));

test("renders ranked story with rationale and selects it", async () => {
  const onSelect = vi.fn();
  render(<QueueView onSelect={onSelect} />);
  expect(await screen.findByText("Jeddah expansion")).toBeInTheDocument();
  expect(screen.getByText(/Largest this year/)).toBeInTheDocument();
  expect(screen.getByText("3 sources")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /select/i }));
  expect(onSelect).toHaveBeenCalledWith(7);
});
```

(`userEvent` needs `@testing-library/user-event` — add `"@testing-library/user-event": "^14.5.0"` to devDependencies.)

- [ ] **Step 3: Run test to verify it fails**

```bash
cd dashboard && npm install && npm test
```
Expected: FAIL — cannot resolve `../QueueView.jsx`.

- [ ] **Step 4: Implement `QueueView.jsx`, `App.jsx`, `styles.css`**

`dashboard/src/views/QueueView.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

const BANDS = { high: "🔴", medium: "🟠", low: "🟢" };

export default function QueueView({ onSelect }) {
  const [stories, setStories] = useState([]);
  const [band, setBand] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    try {
      const data = await apiGet(`/api/queue${band ? `?band=${band}` : ""}`);
      setStories(data.stories);
    } catch (e) { setError(String(e)); }
  }
  useEffect(() => { refresh(); }, [band]);

  async function select(id) {
    await apiPost(`/api/stories/${id}/select`);
    onSelect?.(id);
    refresh();
  }

  return (
    <div className="queue">
      <div className="queue-toolbar">
        {["", "high", "medium", "low"].map((b) => (
          <button key={b} className={band === b ? "active" : ""} onClick={() => setBand(b)}>
            {b || "all"}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {stories.map((s) => (
        <div key={s.id} className={`card band-${s.band}`}>
          <div className="card-head">
            <span className="band">{BANDS[s.band]} {s.band}</span>
            <span className="priority">{s.priority?.toFixed(1)}</span>
            <span className="category">{s.category}</span>
            <span className="sources">{s.n_sources} sources</span>
          </div>
          <h3>{s.title}</h3>
          {s.judge && <p className="rationale">💡 {s.judge.rationale}</p>}
          {s.judge && <p className="gist">{s.judge.gist}</p>}
          <div className="card-actions">
            <button onClick={() => select(s.id)}>Select</button>
            <button onClick={() => onSelect?.(s.id)}>Open</button>
          </div>
        </div>
      ))}
      {!stories.length && !error && <p className="empty">Queue empty — run a fetch.</p>}
    </div>
  );
}
```

`dashboard/src/App.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import QueueView from "./views/QueueView.jsx";
import StoryDetail from "./views/StoryDetail.jsx";
import ReviewView from "./views/ReviewView.jsx";
import PublishedView from "./views/PublishedView.jsx";
import Wizard from "./views/Wizard.jsx";
import { apiGet } from "./api.js";

const TABS = ["queue", "review", "published", "settings"];

export default function App() {
  const [tab, setTab] = useState("queue");
  const [openStory, setOpenStory] = useState(null);
  const [status, setStatus] = useState({});

  useEffect(() => {
    const t = setInterval(async () => {
      try { setStatus(await apiGet("/api/health")); } catch { /* server away */ }
    }, 15000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="app">
      <header>
        <h1>⚡ Supply Chain Sparks</h1>
        <nav>{TABS.map((t) => (
          <button key={t} className={tab === t ? "active" : ""}
                  onClick={() => { setTab(t); setOpenStory(null); }}>{t}</button>
        ))}</nav>
      </header>
      <main>
        {tab === "queue" && (openStory
          ? <StoryDetail storyId={openStory} onBack={() => setOpenStory(null)} />
          : <QueueView onSelect={setOpenStory} />)}
        {tab === "review" && <ReviewView onOpen={setOpenStory} />}
        {tab === "published" && <PublishedView />}
        {tab === "settings" && <Wizard />}
      </main>
      <footer>status: {status.status || "…"} </footer>
    </div>
  );
}
```

`dashboard/src/styles.css` — minimal but present (cards, badges, two-column review grid, `dir="rtl"` support):

```css
:root { --bg:#0f172a; --card:#1e293b; --accent:#fbbf24; --ok:#34d399; --bad:#f87171; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, "Segoe UI", sans-serif; background:var(--bg); color:#e2e8f0; }
.app { display:flex; flex-direction:column; min-height:100vh; }
header { display:flex; justify-content:space-between; align-items:center; padding:.6rem 1rem; background:#111827; }
header nav button { margin-left:.4rem; padding:.3rem .8rem; }
main { flex:1; padding:1rem; max-width:1100px; margin:0 auto; width:100%; }
footer { padding:.4rem 1rem; font-size:.8rem; color:#94a3b8; background:#111827; }
.card { background:var(--card); border-radius:8px; padding:1rem; margin-bottom:.8rem; }
.card-head { display:flex; gap:1rem; font-size:.85rem; color:#94a3b8; }
.priority { color:var(--accent); font-weight:700; }
.rationale { color:#cbd5e1; }
.card-actions button, .queue-toolbar button, nav button { cursor:pointer; }
button.active { outline:2px solid var(--accent); }
.error { color:var(--bad); }
[dir="rtl"] { text-align:right; }
.review-grid { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
textarea { width:100%; min-height:280px; background:#0b1220; color:#e2e8f0; font:inherit; }
.flag { border-left:3px solid var(--bad); padding:.4rem .6rem; margin:.3rem 0; background:#1c1917; }
table { width:100%; border-collapse:collapse; }
th, td { text-align:left; padding:.4rem; border-bottom:1px solid #334155; font-size:.9rem; }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd dashboard && npm test
```
Expected: QueueView test PASSED. (`StoryDetail`/`ReviewView`/`PublishedView`/`Wizard` don't exist yet — App.jsx imports them, so EITHER create empty placeholder files `export default function X() { return null; }` for now and replace them in Task 11, or defer App.jsx imports with `React.lazy`. Use the empty-file approach and replace contents in Task 11.)

- [ ] **Step 6: Commit**

```bash
git add dashboard/
git commit -m "feat: dashboard scaffold with queue view"
```

---

### Task 11: Story detail, Review, Published views + settings/wizard endpoints

**Files:**
- Create (replace placeholders): `dashboard/src/views/StoryDetail.jsx`, `ReviewView.jsx`, `PublishedView.jsx`, `Wizard.jsx`
- Modify: `sparks/server/routes.py` (settings endpoints)
- Test: `dashboard/src/views/__tests__/ReviewView.test.jsx`, `tests/test_server_settings.py`

**Interfaces:**
- Consumes: `GET /api/stories/{id}`, `POST .../generate`, `POST /api/generations/{id}` (edit), `POST /api/generations/{id}/fact-check`, `POST /api/flags/{id}/resolve`, `POST /api/stories/{id}/approve`, `POST .../publish`, `GET /api/publications`, `GET/POST /api/settings`, `GET /api/settings-status`.
- Produces: new backend routes `GET /api/settings-status` → `{"has_api_key": bool, "has_repo": bool, "ollama": bool, "schedule_hours": n}`, `POST /api/settings` accepting `{"api_key"?, "repo_url"?, "git_token"?, "schedule_hours"?}` (secrets persisted to `secrets.yaml` next to `settings.yaml`, never committed), plus frontend views.

- [ ] **Step 1: Backend first — failing test**

`tests/test_server_settings.py`:

```python
import httpx
import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


@pytest.fixture
def env(settings):
    db = Database(settings.db_path)
    tc = TestClient(create_app(settings, db=db))
    return tc, {"X-Sparks-Token": db.get_setting("server_token")}, settings


def test_settings_status_defaults(env):
    tc, h, settings = env
    r = tc.get("/api/settings-status", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["has_api_key"] is False and data["has_repo"] is False
    assert data["schedule_hours"] == 6


def test_settings_status_ollama_detected(env, monkeypatch):
    tc, h, settings = env
    monkeypatch.setattr(httpx, "get",
                        lambda url, **kw: type("R", (), {"status_code": 200})())
    assert tc.get("/api/settings-status", headers=h).json()["ollama"] is True


def test_post_settings_persists_secrets(env):
    tc, h, settings = env
    r = tc.post("/api/settings", headers=h,
                json={"api_key": "sk-new", "repo_url": "https://github.com/o/r.git",
                      "git_token": "gt", "schedule_hours": 4})
    assert r.status_code == 200
    secrets_file = settings.settings_path.parent / "secrets.yaml"
    text = secrets_file.read_text(encoding="utf-8")
    assert "sk-new" in text and "github.com/o/r" in text
    status = tc.get("/api/settings-status", headers=h).json()
    assert status["has_api_key"] and status["has_repo"] and status["schedule_hours"] == 4
```

**Implementation** (append to `routes.py`; `write_secrets` helper in `sparks/config.py`):

```python
# sparks/config.py addition
def write_secrets(settings_path, values: dict) -> None:
    import pathlib, yaml
    path = pathlib.Path(settings_path).parent / "secrets.yaml"
    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data.update({k: v for k, v in values.items() if v is not None})
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def read_secrets(settings_path) -> dict:
    import pathlib, yaml
    path = pathlib.Path(settings_path).parent / "secrets.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
```

```python
# routes.py additions
@router.get("/settings-status")
def settings_status(request: Request):
    import httpx
    from sparks.config import read_secrets
    settings = _settings(request)
    secrets = read_secrets(settings.settings_path)
    ollama = False
    try:
        ollama = httpx.get(f"{settings.judge.local.ollama_url}/api/version",
                           timeout=1.5).status_code == 200
    except Exception:
        pass
    return {"has_api_key": bool(secrets.get("api_key") or settings.judge.api.api_key),
            "has_repo": bool(secrets.get("repo_url") or settings.publish.repo_url),
            "ollama": ollama,
            "schedule_hours": settings.fetch.schedule_hours}


@router.post("/settings")
def post_settings(request: Request, body: dict):
    from sparks.config import write_secrets
    settings = _settings(request)
    secrets = {}
    if "api_key" in body:
        secrets["api_key"] = body["api_key"]
    if "repo_url" in body:
        secrets["repo_url"] = body["repo_url"]
    if "git_token" in body:
        secrets["git_token"] = body["git_token"]
    if secrets:
        write_secrets(settings.settings_path, secrets)
    return {"status": "saved"}
```

Note: `load_settings` gains a final step — merge `read_secrets(path)` overrides into `settings.judge.api.api_key`, `settings.publish.repo_url`, `settings.publish.token` when present. Add to `load_settings` before returning:

```python
    from sparks.config import read_secrets
    for key, target in (("api_key", settings.judge.api),
                        ("repo_url", settings.publish),
                        ("git_token", None)):
        value = secrets.get(key)
        if value is None:
            continue
        if key == "api_key":
            target.api_key = value
        elif key == "repo_url":
            settings.publish.repo_url = value
        else:
            settings.publish.token = value
```

with `secrets = read_secrets(path)` before it. (`ServerConfig`, `PublishConfig`, and `fetch.schedule_hours` were already added to `config.py` in Task 1 — do not re-add them here.)

- [ ] **Step 2: Frontend — failing test**

`dashboard/src/views/__tests__/ReviewView.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, test, expect, beforeEach } from "vitest";
import ReviewView from "../ReviewView.jsx";

const api = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn() }));
vi.mock("../../api.js", () => api);

const STORY = {
  story: { id: 3, title: "T", status: "review", priority: 80 },
  sources: [], judge: null,
  generations: [
    { id: 11, format: "article", language: "en", content: "EN body" },
    { id: 12, format: "article", language: "ar", content: "AR body" },
    { id: 13, format: "linkedin", language: "en", content: "hook\n\ninsight" },
  ],
  open_flags: [{ id: 21, claim: "by 2031", verdict: "unsupported" }],
};

test("approve disabled while flags open, enabled after resolve", async () => {
  api.apiGet.mockImplementation(async (p) =>
    p.includes("flags") ? { open_flags: [] } : { stories: [STORY] });
  // story list first
  render(<ReviewView onOpen={() => {}} />);
  expect(await screen.findByText("T")).toBeInTheDocument();

  // open the story editor view
  await userEvent.click(screen.getByText("T"));
  expect(await screen.findByText("EN body")).toBeInTheDocument();
  expect(screen.getByText(/by 2031/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /approve/i })).toBeDisabled();

  api.apiGet.mockResolvedValue({ ...STORY, open_flags: [] });
  await userEvent.click(screen.getByRole("button", { name: /resolve/i }));
  expect(await screen.findByText(/approve/i)).toBeEnabled();
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd dashboard && npm test    # ReviewView test fails (view not implemented)
python -m pytest tests/test_server_settings.py -v   # backend endpoints missing
```

- [ ] **Step 4: Implement the four views**

`dashboard/src/views/StoryDetail.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function StoryDetail({ storyId, onBack }) {
  const [data, setData] = useState(null);
  const [msg, setMsg] = useState("");

  async function refresh() {
    setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

  if (!data) return <p>loading…</p>;
  const { story, sources, judge, generations } = data;

  async function generate(formats) {
    setMsg("generating…");
    const { job_id } = await apiPost(`/api/stories/${storyId}/generate`, { formats });
    poll(job_id);
  }
  async function poll(jobId) {
    const t = setInterval(async () => {
      const s = await apiGet(`/api/jobs/${jobId}`);
      if (s.state !== "running") { clearInterval(t); setMsg(s.state === "error" ? s.error : "done"); refresh(); }
    }, 1500);
  }

  return (
    <div className="detail">
      <button onClick={onBack}>← back</button>
      <h2>{story.title}</h2>
      <p>{story.band} · {story.priority} · {story.category} · {story.status}</p>
      {judge && (
        <div className="judge-box">
          <p>💡 {judge.rationale_market_impact}</p>
          <p>{judge.gist}</p>
          <small>SC {judge.supply_chain_relevance}/10 · KSA {judge.saudi_gcc_relevance}/10 ·
            Impact {judge.market_impact}/10 · Novelty {judge.novelty}/10</small>
        </div>
      )}
      <div className="sources">
        <h4>Sources 🔒 <small>(local only — never published)</small></h4>
        <ul>{sources.map((s, i) => <li key={i}>{s.name} — {s.url}</li>)}</ul>
      </div>
      <div className="actions">
        <button onClick={() => generate(["article"])}>Generate articles (EN+AR)</button>
        <button onClick={() => generate(["linkedin"])}>Generate LinkedIn (EN+AR)</button>
      </div>
      {msg && <p>{msg}</p>}
      {generations.map((g) => (
        <div key={g.id} className="card">
          <b>{g.format} · {g.language}</b>
          <pre>{g.content}</pre>
        </div>
      ))}
    </div>
  );
}
```

`dashboard/src/views/ReviewView.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function ReviewView({ onOpen }) {
  const [data, setData] = useState(null);

  async function refresh() { setData(await apiGet("/api/queue")); }
  useEffect(() => { refresh(); }, []);
  if (!data) return <p>loading…</p>;

  const selected = data.stories.filter((s) =>
    ["selected", "generating", "review", "approved"].includes(s.status));
  return (
    <div>
      <h2>Review</h2>
      {!selected.length && <p className="empty">Nothing in review — select stories from the queue.</p>}
      {selected.map((s) => (
        <div key={s.id} className="card" onClick={() => onOpen(s.id)}>
          <b>{s.title}</b> <span className="category">{s.status}</span>
        </div>
      ))}
      <StoryEditor onRefresh={refresh} />
    </div>
  );
}

function StoryEditor({ onRefresh }) {
  const [storyId, setStoryId] = useState(null);
  const [data, setData] = useState(null);

  async function refresh() {
    if (storyId) setData(await apiGet(`/api/stories/${storyId}`));
  }
  useEffect(() => { refresh(); }, [storyId]);

  if (!storyId) {
    return <div className="editor"><p>Pick a story above to edit.</p>
      <StoryPicker onPick={setStoryId} /></div>;
  }
  if (!data) return <p>loading…</p>;
  const en = data.generations.find((g) => g.format === "article" && g.language === "en");
  const ar = data.generations.find((g) => g.format === "article" && g.language === "ar");
  const li = data.generations.filter((g) => g.format === "linkedin");
  const blocked = data.open_flags.length > 0 || !data.generations.length;

  async function save(genId, content) { await apiPost(`/api/generations/${genId}`, { content }); refresh(); }
  async function factCheck(genId) { await apiPost(`/api/generations/${genId}/fact-check`); refresh(); }
  async function resolve(id) { await apiPost(`/api/flags/${id}/resolve`, { resolution: "resolved_confirm" }); refresh(); }
  async function approve() { await apiPost(`/api/stories/${storyId}/approve`); refresh(); }
  async function publish(destinations) { await apiPost(`/api/stories/${storyId}/publish`, { destinations }); refresh(); }

  return (
    <div className="editor">
      <div className="review-grid">
        <div>
          <h3>English</h3>
          <EditorArea gen={en} onSave={save} onFactCheck={factCheck} />
        </div>
        <div dir="rtl">
          <h3>العربية</h3>
          <EditorArea gen={ar} onSave={save} onFactCheck={factCheck} />
        </div>
      </div>
      {li.map((g) => (
        <div key={g.id} className="card">
          <b>LinkedIn · {g.language}</b>
          <pre>{g.content}</pre>
          <CopyButton text={g.content} />
          <button onClick={() => publish(["linkedin"])}>Mark copied</button>
        </div>
      ))}
      <h4>Fact flags</h4>
      {data.open_flags.length === 0 && <p className="ok">no open flags ✓</p>}
      {data.open_flags.map((f) => (
        <div key={f.id} className="flag">
          ⚠ <b>{f.claim}</b> — {f.verdict}
          <button onClick={() => resolve(f.id)}>resolve</button>
        </div>
      ))}
      <div className="actions">
        <button disabled={blocked} onClick={approve}>Approve</button>
        <button disabled={data.story.status !== "approved"} onClick={() => publish(["site"])}>
          Publish to site
        </button>
      </div>
    </div>
  );
}

function StoryPicker({ onPick }) {
  const [id, setId] = useState("");
  return <div>
    <input placeholder="story id" value={id} onChange={(e) => setId(e.target.value)} />
    <button onClick={() => onPick(Number(id))}>open</button>
  </div>;
}

function EditorArea({ gen, onSave, onFactCheck }) {
  const [text, setText] = useState(gen?.content || "");
  useEffect(() => { setText(gen?.content || ""); }, [gen?.id]);
  if (!gen) return <p>not generated yet</p>;
  return <div>
    <textarea value={text} onChange={(e) => setText(e.target.value)}
              dir={gen.language === "ar" ? "rtl" : "ltr"} />
    <div className="actions">
      <button onClick={() => onSave(gen.id, text)}>Save</button>
      <button onClick={() => onFactCheck(gen.id)}>Fact-check</button>
      <span className="category">{text.length} chars</span>
    </div>
  </div>;
}

function CopyButton({ text }) {
  const [done, setDone] = useState(false);
  return <button onClick={async () => {
    await navigator.clipboard.writeText(text); setDone(true);
    setTimeout(() => setDone(false), 1500);
  }}>{done ? "copied ✓" : "Copy"}</button>;
}
```

`dashboard/src/views/PublishedView.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import { apiGet } from "../api.js";

export default function PublishedView() {
  const [pubs, setPubs] = useState(null);
  useEffect(() => { apiGet("/api/publications").then((d) => setPubs(d.publications)); }, []);
  if (!pubs) return <p>loading…</p>;
  return (
    <div>
      <h2>Published</h2>
      {!pubs.length && <p className="empty">Nothing published yet.</p>}
      <table>
        <thead><tr><th>when</th><th>title</th><th>destination</th><th>url</th></tr></thead>
        <tbody>{pubs.map((p) => (
          <tr key={p.id}>
            <td>{p.published_at?.replace("T", " ").slice(0, 16)}</td>
            <td>{p.title}</td>
            <td>{p.destination}{p.detail ? ` (${p.detail})` : ""}</td>
            <td>{p.url ? <a href={p.url} target="_blank" rel="noreferrer">{p.url}</a> : "—"}</td>
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}
```

`dashboard/src/views/Wizard.jsx`:

```jsx
import React, { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api.js";

export default function Wizard() {
  const [status, setStatus] = useState(null);
  const [form, setForm] = useState({ api_key: "", repo_url: "", git_token: "",
                                      schedule_hours: 6 });
  const [saved, setSaved] = useState("");

  async function refresh() { setStatus(await apiGet("/api/settings-status")); }
  useEffect(() => { refresh(); }, []);
  if (!status) return <p>loading…</p>;

  async function save() {
    await apiPost("/api/settings", form);
    setSaved("saved ✓");
    refresh();
  }

  return (
    <div className="wizard">
      <h2>Setup</h2>
      <ul>
        <li>{status.has_api_key ? "✓" : "✗"} API key (writer tier)</li>
        <li>{status.has_repo ? "✓" : "✗"} Content repo connected</li>
        <li>{status.ollama ? "✓" : "—"} Ollama local model (optional)</li>
        <li>fetch every {status.schedule_hours}h</li>
      </ul>
      <label>API key <input type="password" value={form.api_key}
        onChange={(e) => setForm({ ...form, api_key: e.target.value })} /></label>
      <label>Content repo URL <input value={form.repo_url}
        onChange={(e) => setForm({ ...form, repo_url: e.target.value })} /></label>
      <label>Git token <input type="password" value={form.git_token}
        onChange={(e) => setForm({ ...form, git_token: e.target.value })} /></label>
      <label>Fetch interval (hours) <input type="number" min="0" value={form.schedule_hours}
        onChange={(e) => setForm({ ...form, schedule_hours: Number(e.target.value) })} /></label>
      <button onClick={save}>Save</button> {saved}
    </div>
  );
}
```

- [ ] **Step 5: Run all tests**

```bash
cd dashboard && npm test
python -m pytest -v
```
Expected: frontend ReviewView test green; full Python suite green.

- [ ] **Step 6: Commit**

```bash
git add dashboard/ sparks/server/routes.py sparks/config.py tests/test_server_settings.py
git commit -m "feat: review/published/wizard views and settings endpoints"
```

---

### Task 12: Packaging (PyInstaller + Inno Setup)

**Files:**
- Create: `sparks_exe.spec`, `installer.iss`, `scripts/build.ps1`, `scripts/verify_build.ps1`
- No automated tests (packaging) — scripted verification instead.

**Interfaces:**
- Consumes: everything.
- Produces: `dist/SupplyChainSparks/SupplyChainSparks.exe` + `dist/SupplyChainSparks-Setup.exe`.

- [ ] **Step 1: `sparks_exe.spec`**

```python
# PyInstaller spec — one-folder build with bundled dashboard + prompts.
import pathlib

root = pathlib.Path(SPECPATH).resolve()
datas = [
    (str(root / "dashboard" / "dist"), "dashboard/dist"),
    (str(root / "sparks" / "prompts"), "sparks/prompts"),
    (str(root / "settings.yaml"), "."),
    (str(root / "sources.yaml"), "."),
]
hiddenimports = [
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "apscheduler.schedulers.background", "pystray._win32",
]
a = Analysis(["sparks/app/launch.py"], pathex=[str(root)], datas=datas,
             hiddenimports=hiddenimports, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="SupplyChainSparks",
          console=False, icon=None)
coll = COLLECT(exe, a.binaries, a.datas, name="SupplyChainSparks")
```

Create `sparks/app/launch.py` (windowed entry that avoids console flash):

```python
"""Packaged entry point: redirects straight to sparks.app.main.run()."""
from sparks.app.main import run

if __name__ == "__main__":
    raise SystemExit(run())
```

- [ ] **Step 2: `installer.iss`**

```ini
[Setup]
AppName=Supply Chain Sparks
AppVersion=0.1.0
DefaultDirName={localappdata}\SupplyChainSparks
DefaultGroupName=Supply Chain Sparks
PrivilegesRequired=lowest
OutputBaseFilename=SupplyChainSparks-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "dist\SupplyChainSparks\*"; DestDir: "{app}"; Flags: recursesubdirs

[Icons]
Name: "{group}\Supply Chain Sparks"; Filename: "{app}\SupplyChainSparks.exe"
Name: "{commondesktop}\Supply Chain Sparks"; Filename: "{app}\SupplyChainSparks.exe"

[Run]
Filename: "{app}\SupplyChainSparks.exe"; Description: "Launch Supply Chain Sparks"; Flags: nowait postinstall skipifsilent
```

- [ ] **Step 3: `scripts/build.ps1` and `scripts/verify_build.ps1`**

```powershell
# scripts/build.ps1 — full release build. Run from repo root.
$ErrorActionPreference = "Stop"
Push-Location dashboard
npm ci
npm run build
Pop-Location
python -m PyInstaller sparks_exe.spec --noconfirm --clean
if ($env:INNO_SETUP_PATH) {
    & "$env:INNO_SETUP_PATH\ISCC.exe" installer.iss
} else {
    Write-Warning "INNO_SETUP_PATH not set - skipping installer (run ISCC on installer.iss)"
}
```

```powershell
# scripts/verify_build.ps1 — smoke: start exe, poll health, kill.
$ErrorActionPreference = "Stop"
$proc = Start-Process -FilePath "dist\SupplyChainSparks\SupplyChainSparks.exe" -PassThru
try {
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8765/api/health" -UseBasicParsing
            if ($r.StatusCode -eq 401) { $ok = $true; break }
        } catch {}
    }
    if (-not $ok) { throw "health endpoint did not come up (401 expected without token)" }
    Write-Host "BUILD OK - server up, auth enforced"
} finally {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
```

- [ ] **Step 4: Build and verify**

```powershell
pip install pyinstaller
powershell -ExecutionPolicy Bypass -File scripts/build.ps1
powershell -ExecutionPolicy Bypass -File scripts/verify_build.ps1
```

Expected: dashboard builds, PyInstaller produces `dist/SupplyChainSparks/`, verify prints `BUILD OK - server up, auth enforced`. Manually confirm: tray icon appears, window opens, wizard shows, quit via tray works, second launch exits immediately (single instance).

- [ ] **Step 5: Commit**

```bash
git add sparks_exe.spec installer.iss scripts/ sparks/app/launch.py
git commit -m "feat: pyinstaller and inno setup packaging"
```

---

## Plan 2 completion checklist

After Task 12 the full v1 loop works locally: scheduled/manual fetch → ranked queue → select → bilingual generation → fact-check gate → edit → approve → publish to content repo (site live after Plan 3 deploy) → LinkedIn copy + Published archive. Success criteria 1–3 of the spec are measurable end-to-end; criterion 4 (clean 8 GB machine) is proven by installing `SupplyChainSparks-Setup.exe` on a machine without developer tools — the exe bundles Python, the dashboard, dulwich; only optional Ollama is external.





