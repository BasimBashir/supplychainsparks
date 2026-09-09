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
    settings.judge.default_tier = "api"
    settings.judge.api.base_url = "https://api.example/v4"
    settings.judge.api.api_key = "test-key"
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
