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
