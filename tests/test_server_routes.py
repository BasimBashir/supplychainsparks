from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.models import FetchedEntry, Source
from sparks.server.app import create_app

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


@pytest.fixture
def env(settings):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="Reuters", kind="rss", url="https://r.com/rss",
                                  credibility=0.8))
    iid = db.insert_item(sid, FetchedEntry("https://r.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    story_id = db.create_story("Jeddah expansion", iid)
    from sparks.judge.schema import JudgeOutput
    db.save_judge_score(story_id, tier="api", model="qwen/qwen3-235b-a22b",
                        prompt_version="judge_v1",
                        output=JudgeOutput(
                            supply_chain_relevance=9, saudi_gcc_relevance=10,
                            market_impact=8, novelty=7,
                            rationale_supply_chain="core port capex",
                            rationale_saudi_gcc="KSA project",
                            rationale_market_impact="largest this year",
                            rationale_novelty="first report",
                            suggested_category="ports-shipping",
                            gist="Mawani expands Jeddah capacity."))
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, 88.0, "high", "ports-shipping")
    app = create_app(settings, db=db)
    tc = TestClient(app)
    headers = {"X-Sparks-Token": db.get_setting("server_token")}
    return tc, headers, db, story_id


def test_queue_endpoint(env):
    tc, h, db, story_id = env
    r = tc.get("/api/queue", headers=h)
    assert r.status_code == 200
    data = r.json()["stories"]
    assert data[0]["title"] == "Jeddah expansion"
    assert data[0]["priority"] == 88.0 and data[0]["n_sources"] == 1
    assert "rationale" in data[0]["judge"]  # explainability payload


def test_story_detail_includes_local_only_sources(env):
    tc, h, db, story_id = env
    r = tc.get(f"/api/stories/{story_id}", headers=h)
    assert r.status_code == 200
    detail = r.json()
    assert detail["sources"][0]["name"] == "Reuters"
    assert detail["sources"][0]["local_only"] is True
    assert detail["story"]["status"] == "ranked"


def test_select_and_fetch_now(env, monkeypatch):
    tc, h, db, story_id = env
    assert tc.post(f"/api/stories/{story_id}/select", headers=h).status_code == 200
    assert db.get_story(story_id).status == "selected"

    import sparks.server.routes as routes
    monkeypatch.setattr(routes, "run_cycle",
                        lambda s: type("R", (), {"errors": [], "items_new": 1,
                                                 "stories_created": 0,
                                                 "stories_judged": 0,
                                                 "stories_ranked": 0})())
    r = tc.post("/api/fetch-now", headers=h)
    job_id = r.json()["job_id"]
    for _ in range(100):
        if tc.get(f"/api/jobs/{job_id}", headers=h).json()["state"] != "running":
            break
    assert tc.get(f"/api/jobs/{job_id}", headers=h).json()["state"] == "done"


def test_queue_unscored_band_and_count(env):
    """Unscored stories must be visible in the app, not a silent empty queue."""
    tc, h, db, story_id = env
    sid2 = db.upsert_source(Source(name="AP", kind="rss", url="https://ap.com/rss"))
    iid2 = db.insert_item(sid2, FetchedEntry("https://ap.com/b", "Red Sea attack", NOW),
                          "raw", NOW)
    story2 = db.create_story("Red Sea attack", iid2)
    db.set_story_judge_status(story2, "unscored")

    all_q = tc.get("/api/queue", headers=h).json()
    assert all_q["unscored_count"] == 1
    assert "Red Sea attack" not in [s["title"] for s in all_q["stories"]]

    unscored = tc.get("/api/queue?band=unscored", headers=h).json()["stories"]
    assert [s["title"] for s in unscored] == ["Red Sea attack"]
    assert unscored[0]["band"] == "unscored"
    assert unscored[0]["judge"] is None and unscored[0]["priority"] is None


def test_delete_story_removes_story_and_items(env):
    tc, h, db, story_id = env
    assert tc.get(f"/api/stories/{story_id}", headers=h).status_code == 200
    r = tc.post(f"/api/stories/{story_id}/delete", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "deleted"
    assert db.get_story(story_id) is None
    assert db.latest_judge(story_id) is None
    assert db.story_members(story_id) == []          # items went with it
    assert tc.get(f"/api/stories/{story_id}", headers=h).status_code == 404
    assert tc.post(f"/api/stories/{story_id}/delete", headers=h).status_code == 404


def test_delete_story_refuses_published(env):
    tc, h, db, story_id = env
    db.set_story_status(story_id, "published")
    r = tc.post(f"/api/stories/{story_id}/delete", headers=h)
    assert r.status_code == 409
    assert db.get_story(story_id) is not None        # still there
