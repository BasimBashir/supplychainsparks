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
