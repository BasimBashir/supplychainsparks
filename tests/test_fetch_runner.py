from pathlib import Path

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
    # freeze politeness so no real sleeping happens in tests
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
    assert db.fetch_runs(items[0].source_id)[0]["status"] == "ok"


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
