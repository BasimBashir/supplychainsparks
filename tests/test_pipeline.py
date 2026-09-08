from datetime import datetime, timezone
from pathlib import Path

import pytest

from sparks.db import Database
from sparks.judge.schema import JudgeOutput
from sparks.models import FetchedEntry, Source, SourceRun
from sparks.pipeline import run_cycle

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)

VALID = JudgeOutput(supply_chain_relevance=9, saudi_gcc_relevance=10, market_impact=8,
                    novelty=7, rationale_supply_chain="r", rationale_saudi_gcc="r",
                    rationale_market_impact="r", rationale_novelty="r",
                    suggested_category="ports-shipping", gist="Mawani expands Jeddah.")


class FakeJudge:
    def judge(self, ctx, settings=None):
        return VALID


class FakeFetchRunner:
    """Inserts 3 feed items: two near-duplicates + one distinct."""
    def __init__(self, settings, db):
        self.settings, self.db = settings, db

    def run(self, sources=None):
        sid = self.db.upsert_source(Source(name="Ex", kind="rss",
                                           url="https://feed.example/rss"))
        entries = [
            FetchedEntry("https://pub.com/a", "Jeddah terminal expansion announced", NOW),
            FetchedEntry("https://pub.com/b", "Jeddah terminal expansion announced!", NOW),
            FetchedEntry("https://pub.com/c", "Dammam warehouses at record occupancy", NOW),
        ]
        run = SourceRun(source_id=sid, source_name="Ex", status="ok",
                        items_found=3, items_new=0)
        for e in entries:
            if self.db.insert_item(sid, e, raw_path="pending", fetched_at=NOW):
                run.items_new += 1
        return [run]


class FakeContentFetcher:
    """Fills extraction without network: fixture text for Jeddah items,
    a distinct body for the Dammam item (so simhash doesn't merge them)."""
    def __init__(self, settings, db):
        self.settings, self.db = settings, db

    def fetch_article(self, item):
        from sparks.extract import extract_article
        if item.title and "Dammam" in item.title:
            text = "Dammam warehouse occupancy reached record levels this quarter. " * 30
            self.db.update_item_extraction(item.id, text, None, len(text.split()))
        else:
            good = (FIXTURES / "article_good.html").read_text(encoding="utf-8")
            extracted = extract_article(good)
            self.db.update_item_extraction(item.id, extracted.text, None,
                                           extracted.word_count)
        return True


def test_run_cycle_full_happy_path(settings):
    db = Database(settings.db_path)
    report = run_cycle(settings, db=db,
                       fetch_runner=FakeFetchRunner(settings, db),
                       content_fetcher=FakeContentFetcher(settings, db),
                       api_judge=FakeJudge(), local_judge=FakeJudge())
    assert report.finished_at is not None
    assert report.items_new == 3
    assert report.stories_created == 2      # near-duplicates merged
    assert report.stories_judged >= 1
    assert report.stories_ranked >= 1
    queue = db.queue_stories()
    assert len(queue) == 2
    top = queue[0]
    assert top.band in ("high", "medium")
    assert top.judge_status in ("api", "local")
    assert top.n_sources == 2              # merged cluster


def test_run_cycle_isolates_fetch_errors(settings):
    class ExplodingRunner:
        def run(self, sources=None):
            run = SourceRun(source_id=1, source_name="Boom", status="error", items_found=0,
                            error="HTTPError: 500")
            return [run]

    db = Database(settings.db_path)
    report = run_cycle(settings, db=db, fetch_runner=ExplodingRunner(),
                       content_fetcher=FakeContentFetcher(settings, db),
                       api_judge=FakeJudge(), local_judge=FakeJudge())
    assert report.errors == ["HTTPError: 500"]
    assert report.stories_created == 0


# ---------------- replay (Task 12) ----------------

from sparks.fetch.runner import save_raw  # noqa: E402
from sparks.pipeline import replay  # noqa: E402


def _seed_cycle(settings, db):
    """Items with fixture-backed raw files so replay can re-read them from disk."""
    sid = db.upsert_source(Source(name="Ex", kind="rss", url="https://feed.example/rss"))
    good_bytes = (FIXTURES / "article_good.html").read_bytes()
    variant_bytes = (FIXTURES / "article_variant.html").read_bytes()
    raw_good = save_raw(settings.raw_dir, "https://pub.com/a", good_bytes)
    raw_variant = save_raw(settings.raw_dir, "https://pub.com/b", variant_bytes)
    for url, title, raw in [
        ("https://pub.com/a", "Jeddah terminal expansion announced", raw_good),
        ("https://pub.com/b", "Jeddah terminal expansion announced!", raw_variant),
    ]:
        iid = db.insert_item(sid, FetchedEntry(url, title, NOW), str(raw), NOW)
        db.update_item_extraction(iid, (FIXTURES / "article_good.html").read_text("utf-8"),
                                  None, 200)  # placeholder; replay overwrites from raw
    from sparks.dedupe import build_clusters
    items = db.window_items(days=7)
    for cluster in build_clusters(items):
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
    from sparks.judge.service import JudgeService
    service = JudgeService(settings, db, api_judge=FakeJudge(), local_judge=FakeJudge())
    service.judge_pending()
    from sparks.pipeline import _rank_all
    _rank_all(db, settings)  # give the story a ranked priority so replay can change it


def test_replay_reuses_judge_cache_and_reranks(settings):
    db = Database(settings.db_path)
    _seed_cycle(settings, db)
    old_priority = db.queue_stories()[0].priority

    settings.rank.rubric_scale = 5.0  # change config, expect different priorities
    report = replay(settings, db=db, skip_judge=True)

    queue = db.queue_stories()
    assert len(queue) == 1                      # the two items re-merged into one story
    assert queue[0].priority != old_priority
    assert db.latest_judge(queue[0].id).gist == "Mawani expands Jeddah."  # cache restored
    assert report.stories_ranked == 1


def test_replay_reextracts_from_raw(settings):
    db = Database(settings.db_path)
    _seed_cycle(settings, db)
    db.wipe_derived()
    assert db.window_items(days=7)[0].extracted_text is None
    replay(settings, db=db, skip_judge=True)
    items = db.window_items(days=7)
    assert all(i.extracted_text and "Jeddah" in i.extracted_text for i in items)
