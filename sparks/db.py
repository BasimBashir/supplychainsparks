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
CREATE TABLE IF NOT EXISTS settings_kv (
    key TEXT PRIMARY KEY,
    value TEXT
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

    def unextracted_items(self) -> list[ItemRecord]:
        rows = self.conn.execute(
            "SELECT * FROM items WHERE extracted_text IS NULL AND status != 'failed'"
            " ORDER BY id").fetchall()
        return [self._row_to_item(r) for r in rows]

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
             + (f" LIMIT {int(limit)}" if limit else ""))
        return [self._row_to_story(r) for r in self.conn.execute(q).fetchall()]

    def queue_stories(self, limit: int = 50, band: str | None = None) -> list[StoryRecord]:
        q = ("SELECT * FROM stories WHERE status='ranked'"
             + (" AND band=?" if band else "")
             + " ORDER BY priority DESC" + f" LIMIT {int(limit)}")
        params = (band,) if band else ()
        return [self._row_to_story(r) for r in self.conn.execute(q, params).fetchall()]

    def set_story_judge_status(self, story_id: int, judge_status: str) -> None:
        self.conn.execute("UPDATE stories SET judge_status=?, updated_at=? WHERE id=?",
                          (judge_status, datetime.now(timezone.utc).isoformat(), story_id))
        self.conn.commit()

    def set_story_ranking(self, story_id: int, priority: float, band: str, category: str) -> None:
        self.conn.execute(
            "UPDATE stories SET priority=?, band=?, category=?, status='ranked',"
            " updated_at=? WHERE id=?",
            (priority, band, category, datetime.now(timezone.utc).isoformat(), story_id))
        self.conn.commit()

    def all_stories(self) -> list[StoryRecord]:
        rows = self.conn.execute("SELECT * FROM stories ORDER BY id").fetchall()
        return [self._row_to_story(r) for r in rows]

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
        r = self.conn.execute(
            "SELECT * FROM judge_scores WHERE story_id=? ORDER BY id DESC LIMIT 1",
            (story_id,)).fetchone()
        return self._row_to_judge(r) if r else None

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
