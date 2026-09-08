import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from sparks.db import Database
from sparks.generate.service import GenerationService
from sparks.models import FetchedEntry, Source

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
    settings.judge.api.base_url = "https://api.example/v4"
    settings.judge.api.api_key = "test-key"
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
    route.side_effect = [httpx.Response(200, json=_reply(ARTICLE)),
                         httpx.Response(200, json=_reply(SEO)),
                         httpx.Response(200, json=_reply(ARTICLE)),
                         httpx.Response(200, json=_reply(SEO)),
                         httpx.Response(200, json=_reply(LINKEDIN)),
                         httpx.Response(200, json=_reply(LINKEDIN))]
    # API call order: article-en, seo-en, article-ar, seo-ar, linkedin-en, linkedin-ar
    # DB rows: 4 generations (SEO stored as columns on each article row)
    gen_ids = GenerationService(settings, db).generate_for_story(story_id)
    assert len(gen_ids) == 4
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
