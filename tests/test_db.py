from datetime import datetime, timezone

import pytest

from sparks.db import Database
from sparks.models import FetchedEntry, Source

try:
    from sparks.judge.schema import JudgeOutput
except ModuleNotFoundError:  # Task 7 not implemented yet: duck-typed stand-in
    from types import SimpleNamespace

    def JudgeOutput(**kw):  # noqa: N802
        return SimpleNamespace(**kw)

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
    assert [r["status"] for r in runs] == ["ok", "error"]


def test_mark_source_health_and_disable(db):
    sid = _source(db)
    db.mark_source_health(sid, healthy=False)
    db.set_source_fetched(sid)
    src = db.get_source(sid)
    assert src.healthy is False and src.last_fetch_at is not None
    db.upsert_source(Source(name="Test Feed", kind="rss",
                            url="https://example.com/Test-Feed", enabled=False))
    assert db.all_sources(enabled_only=True) == []
