"""Web-search sources (kind='search'): a user-chosen topic queried via
DuckDuckGo News (ddgs lib, no API key) — snippets judge when pages block us."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlite3

from sparks.db import SCHEMA, Database
from sparks.fetch.runner import ContentFetcher, FetchRunner
from sparks.models import FetchedEntry, Source


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


class FakeSearch:
    """Stands in for sparks.fetch.search.search_news — no network."""

    def __init__(self, entries):
        self.entries = entries
        self.calls = []

    def __call__(self, topic, max_results):
        self.calls.append((topic, max_results))
        return self.entries[:max_results]


def _entry(url, title, summary="Snippet about the story with several words to judge."):
    return FetchedEntry(url=url, title=title, summary=summary,
                        published_at=datetime(2026, 9, 8, tzinfo=timezone.utc))


def test_search_news_maps_ddg_fields(monkeypatch):
    from sparks.fetch import search as search_mod

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def news(self, topic, max_results):
            assert topic == "Red Sea shipping"
            return [
                {"date": "2026-09-08T15:01:46+00:00",
                 "title": "Houthi attack disrupts Red Sea traffic",
                 "body": "Tanker traffic through the Bab al-Mandab strait halted.",
                 "url": "https://news.example/story", "source": "Reuters"},
                {"title": "No url — skipped", "body": "", "url": "",
                 "date": "not-a-date"},
            ]

    monkeypatch.setattr(search_mod, "DDGS", FakeDDGS)
    entries = search_mod.search_news("Red Sea shipping", max_results=5)
    assert len(entries) == 1
    e = entries[0]
    assert e.url == "https://news.example/story"
    assert e.title == "Houthi attack disrupts Red Sea traffic"
    assert e.summary == "Tanker traffic through the Bab al-Mandab strait halted."
    assert e.published_at == datetime(2026, 9, 8, 15, 1, 46, tzinfo=timezone.utc)


def test_runner_search_source_creates_items_with_snippet(db, settings):
    search = FakeSearch([_entry("https://news.example/a", "Tanker rerouted"),
                         _entry("https://news.example/b", "Port congestion")])
    db.upsert_source(Source(name="Red Sea watch", kind="search",
                            url="Red Sea shipping attacks"))
    runs = FetchRunner(settings, db, search=search).run()

    assert runs[0].status == "ok"
    assert runs[0].items_found == 2 and runs[0].items_new == 2
    assert search.calls == [("Red Sea shipping attacks",
                             settings.fetch.max_items_per_source)]
    items = db.window_items(days=7)
    assert sorted(i.url for i in items) == ["https://news.example/a",
                                            "https://news.example/b"]
    assert all(i.summary.startswith("Snippet") for i in items)
    assert Path(items[0].raw_path).exists()  # search page archived for replay/audit
    assert db.get_source(items[0].source_id).healthy is True


def test_runner_search_error_is_isolated(db, settings):
    def boom(topic, max_results):
        raise RuntimeError("ddgs rate limited")

    db.upsert_source(Source(name="Topic watch", kind="search", url="Saudi ports"))
    runs = FetchRunner(settings, db, search=boom).run()
    assert runs[0].status == "error"
    assert "ddgs rate limited" in runs[0].error
    assert db.all_sources()[0].healthy is False


class _Response:
    def __init__(self, text, content):
        self.text = text
        self.content = content

    def raise_for_status(self):
        pass


def _item(db, source_id, url, summary=""):
    db.insert_item(source_id, FetchedEntry(url=url, title="Story", summary=summary),
                   raw_path="unused", fetched_at=datetime.now(timezone.utc))
    return db.unextracted_items()[0]


def test_content_fetcher_snippet_fallback_for_search_items(db, settings):
    class RobotsBlock:  # robots.txt disallows everything; article never fetched
        def get(self, url):
            return _Response("User-agent: *\nDisallow: /", b"")

    snippet = ("Jeddah Islamic Port reported record container volumes this "
               "quarter, driven by Red Sea shipping shifts.")
    sid = db.upsert_source(Source(name="Topic watch", kind="search", url="Saudi ports"))
    item = _item(db, sid, "https://blocked.example/article", summary=snippet)

    ok = ContentFetcher(settings, db, client=RobotsBlock()).fetch_article(item)
    assert ok is True
    row = db.window_items(days=7)[0]
    assert row.status == "extracted"
    assert row.extracted_text == snippet
    assert row.word_count == len(snippet.split())


def test_content_fetcher_no_snippet_fallback_for_rss(db, settings):
    class EmptyPage:  # robots allow; page extracts nothing (paywall stub)
        def get(self, url):
            return _Response("User-agent: *\nAllow: /",
                             b"<html><body><p>Subscriber access only.</p></body></html>")

    sid = db.upsert_source(Source(name="Feed", kind="rss", url="https://f.example/rss"))
    item = _item(db, sid, "https://f.example/paywalled-stub",
                 summary="Subscriber only boilerplate text repeated on every page here.")
    ok = ContentFetcher(settings, db, client=EmptyPage()).fetch_article(item)
    assert ok is False
    assert db.window_items(days=7)[0].status == "failed"


def test_content_fetcher_short_snippet_still_fails(db, settings):
    class RobotsBlock:
        def get(self, url):
            return _Response("User-agent: *\nDisallow: /", b"")

    sid = db.upsert_source(Source(name="Topic watch", kind="search", url="Saudi ports"))
    item = _item(db, sid, "https://blocked.example/article", summary="Too short.")
    ok = ContentFetcher(settings, db, client=RobotsBlock()).fetch_article(item)
    assert ok is False
    assert db.window_items(days=7)[0].status == "failed"


# --- schema migration: v2 databases (installed copies) gain 'search' + summary ---
OLD_SCHEMA = (SCHEMA
              .replace("'rss', 'html', 'search'", "'rss', 'html'")
              .replace("summary TEXT,", ""))


def test_migration_opens_v2_databases(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(OLD_SCHEMA)
    conn.execute("INSERT INTO sources (name, kind, url) "
                 "VALUES ('Feed', 'rss', 'https://x.example/rss')")
    conn.execute("INSERT INTO items (source_id, url, url_key, fetched_at, raw_path) "
                 "VALUES (1, 'https://x.example/a', 'x/a', '2026-09-08T00:00:00+00:00', 'r')")
    conn.execute("PRAGMA user_version=2")
    conn.commit()
    conn.close()

    db = Database(path)  # runs schema + migration
    sid = db.upsert_source(Source(name="Topic watch", kind="search",
                                  url="Red Sea shipping"))
    assert db.get_source(sid).kind == "search"  # old CHECK would reject this

    db.insert_item(sid, FetchedEntry(url="https://n.example/a", title="T",
                                     summary="snip"), raw_path="r2",
                   fetched_at=datetime.now(timezone.utc))
    items = db.window_items(days=3650)
    old_row = [i for i in items if i.url == "https://x.example/a"][0]
    assert old_row.summary is None  # pre-existing rows read fine
    new_row = [i for i in items if i.url == "https://n.example/a"][0]
    assert new_row.summary == "snip"
