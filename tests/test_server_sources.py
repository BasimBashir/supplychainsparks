from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


def env(settings):
    db = Database(settings.db_path)
    tc = TestClient(create_app(settings, db=db))
    return tc, {"X-Sparks-Token": db.get_setting("server_token")}, db


def test_add_source_roundtrip(settings):
    tc, h, db = env(settings)
    r = tc.post("/api/sources", headers=h, json={
        "name": "Custom feed", "kind": "rss", "url": "https://example.com/rss",
        "credibility": 0.7, "category_hint": "logistics"})
    assert r.status_code == 200
    assert r.json()["status"] == "added"
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    match = [s for s in listed if s["name"] == "Custom feed"]
    assert match and match[0]["url"] == "https://example.com/rss"
    assert match[0]["enabled"] is True


def test_add_same_url_updates_not_duplicates(settings):
    tc, h, db = env(settings)
    tc.post("/api/sources", headers=h, json={
        "name": "Feed", "kind": "rss", "url": "https://x.com/rss"})
    tc.post("/api/sources", headers=h, json={
        "name": "Feed renamed", "kind": "rss", "url": "https://x.com/rss"})
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    assert len([s for s in listed if "x.com" in s["url"]]) == 1


def test_add_source_validates_kind_and_url(settings):
    tc, h, db = env(settings)
    bad_kind = tc.post("/api/sources", headers=h,
                       json={"name": "x", "kind": "ftp", "url": "https://x.com/rss"})
    bad_url = tc.post("/api/sources", headers=h,
                      json={"name": "x", "kind": "rss", "url": "not-a-url"})
    missing = tc.post("/api/sources", headers=h, json={"kind": "rss"})
    assert bad_kind.status_code == 400
    assert bad_url.status_code == 400
    assert missing.status_code == 400


def test_toggle_source_enable_disable(settings):
    tc, h, db = env(settings)
    r = tc.post("/api/sources", headers=h, json={
        "name": "Feed", "kind": "rss", "url": "https://x.com/rss"})
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    sid = [s for s in listed if s["name"] == "Feed"][0]["id"]

    off = tc.post(f"/api/sources/{sid}/toggle", headers=h, json={"enabled": False})
    assert off.status_code == 200
    # disabled sources stay visible in the list (enabled_only=False)...
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    row = [s for s in listed if s["id"] == sid][0]
    assert row["enabled"] is False
    # ...but are not fetched
    assert db.all_sources(enabled_only=True) == [
        s for s in db.all_sources(enabled_only=False) if s.id != sid]

    on = tc.post(f"/api/sources/{sid}/toggle", headers=h, json={"enabled": True})
    assert on.status_code == 200
    assert [s for s in db.all_sources(enabled_only=True) if s.id == sid]


def _source_with_item(db, name="Feed", url="https://x.com/rss", item_url="https://x.com/a"):
    from datetime import datetime, timezone
    from sparks.models import FetchedEntry, Source
    sid = db.upsert_source(Source(name=name, kind="rss", url=url))
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)
    iid = db.insert_item(sid, FetchedEntry(item_url, "story", now), "raw/x.html", now)
    return sid, iid


def test_delete_source_removes_items_and_emptied_stories(settings):
    tc, h, db = env(settings)
    sid, iid = _source_with_item(db)
    story_id = db.create_story(title="story", primary_item_id=iid)

    r = tc.post(f"/api/sources/{sid}/delete", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    assert db.get_source(sid) is None
    assert db.get_story(story_id) is None        # emptied story purged
    assert db.conn.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0

    missing = tc.post(f"/api/sources/{sid}/delete", headers=h)
    assert missing.status_code == 404


def test_add_search_source_with_topic(settings):
    tc, h, db = env(settings)
    r = tc.post("/api/sources", headers=h, json={
        "name": "Red Sea watch", "kind": "search", "topic": "Red Sea shipping attacks",
        "credibility": 0.6})
    assert r.status_code == 200
    assert r.json()["status"] == "added"
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    match = [s for s in listed if s["name"] == "Red Sea watch"]
    assert match and match[0]["kind"] == "search"
    assert match[0]["url"] == "Red Sea shipping attacks"  # topic stored in url
    # ...and it is fetched like any other source
    assert [s for s in db.all_sources(enabled_only=True) if s.kind == "search"]


def test_add_search_source_requires_topic(settings):
    tc, h, db = env(settings)
    no_topic = tc.post("/api/sources", headers=h, json={"name": "x", "kind": "search"})
    empty_topic = tc.post("/api/sources", headers=h,
                          json={"name": "x", "kind": "search", "topic": "  "})
    assert no_topic.status_code == 400
    assert empty_topic.status_code == 400


def test_toggle_requires_valid_body(settings):
    tc, h, db = env(settings)
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    assert listed == []
    r = tc.post("/api/sources/999/toggle", headers=h, json={"enabled": False})
    assert r.status_code == 404
