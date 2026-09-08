from datetime import datetime, timezone

import pytest

from sparks.db import Database
from sparks.judge.schema import JudgeError, JudgeOutput, StoryContext
from sparks.judge.service import JudgeService
from sparks.models import FetchedEntry, Source

VALID = JudgeOutput(supply_chain_relevance=9, saudi_gcc_relevance=10, market_impact=8,
                    novelty=7, rationale_supply_chain="r", rationale_saudi_gcc="r",
                    rationale_market_impact="r", rationale_novelty="r",
                    suggested_category="ports-shipping", gist="g")


class FakeJudge:
    def __init__(self, raise_=None):
        self.raise_ = raise_
        self.calls = []

    def judge(self, ctx, settings=None):
        self.calls.append(ctx)
        if self.raise_:
            raise self.raise_
        return VALID


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "test.db")


def _story(db):
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    sid = db.upsert_source(Source(name="S", kind="rss", url="https://s.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://s.com/a", "Jeddah expansion", now),
                         "raw/a.html", now)
    db.update_item_extraction(iid, text="First sentence here. Second sentence. " + "word " * 200,
                              language=None, word_count=205)
    return db.create_story(title="Jeddah expansion", primary_item_id=iid)


def test_api_tier_success(db, settings):
    settings.judge.default_tier = "api"  # conftest fixture defaults to local
    story_id = _story(db)
    api = FakeJudge()
    tier = JudgeService(settings, db, api_judge=api, local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "api"
    assert api.calls[0].title == "Jeddah expansion"
    assert api.calls[0].lead.startswith("First sentence here.")
    assert db.latest_judge(story_id).tier == "api"


def test_fallback_to_local_when_api_fails(db, settings):
    settings.judge.default_tier = "api"
    story_id = _story(db)
    local = FakeJudge()
    tier = JudgeService(settings, db, api_judge=FakeJudge(raise_=JudgeError("boom")),
                        local_judge=local).judge_story(story_id)
    assert tier == "local" and len(local.calls) == 1


def test_local_disabled_and_api_fails_marks_unscored(db, settings):
    settings.judge.default_tier = "api"
    settings.judge.local.enabled = False
    story_id = _story(db)
    tier = JudgeService(settings, db, api_judge=FakeJudge(raise_=JudgeError("boom")),
                        local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "unscored"
    assert db.pending_stories() == []  # no longer pending: marked
    assert db.latest_judge(story_id) is None


def test_local_tier_used_when_default(db, settings):
    settings.judge.default_tier = "local"
    story_id = _story(db)
    api = FakeJudge()
    tier = JudgeService(settings, db, api_judge=api,
                        local_judge=FakeJudge()).judge_story(story_id)
    assert tier == "local" and api.calls == []


def test_judge_pending_counts(db, settings):
    _story(db)
    judged, unscored = JudgeService(settings, db, api_judge=FakeJudge(),
                                    local_judge=FakeJudge()).judge_pending()
    assert (judged, unscored) == (1, 0)
