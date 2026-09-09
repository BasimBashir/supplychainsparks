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


def test_toggle_requires_valid_body(settings):
    tc, h, db = env(settings)
    listed = tc.get("/api/sources", headers=h).json()["sources"]
    assert listed == []
    r = tc.post("/api/sources/999/toggle", headers=h, json={"enabled": False})
    assert r.status_code == 404
