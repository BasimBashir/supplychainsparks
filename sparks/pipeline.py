"""Pipeline orchestration: fetch -> content -> extract -> cluster -> judge -> rank."""
from __future__ import annotations

from datetime import datetime, timezone

from sparks.config import Settings
from sparks.db import Database
from sparks.dedupe import build_clusters
from sparks.fetch.runner import ContentFetcher, FetchRunner
from sparks.judge.service import JudgeService
from sparks.models import CycleReport
from sparks.rank import band_for, compute_priority


def run_cycle(settings: Settings, db: Database | None = None,
              fetch_runner=None, content_fetcher=None, judge_service=None,
              api_judge=None, local_judge=None) -> CycleReport:
    db = db or Database(settings.db_path)
    report = CycleReport(started_at=datetime.now(timezone.utc))
    runner = fetch_runner or FetchRunner(settings, db)
    fetcher = content_fetcher or ContentFetcher(settings, db)

    runs = runner.run()
    report.runs = runs
    report.errors = [r.error for r in runs if r.error]
    report.items_new = sum(r.items_new for r in runs)

    for item in db.unextracted_items():
        fetcher.fetch_article(item)

    all_items = db.window_items(days=7, extracted_only=True)
    clustered_ids = {it.id for it in all_items if it.story_id is not None}
    for cluster in build_clusters(all_items):
        if cluster.primary_item_id in clustered_ids:
            continue  # story already exists for this cluster
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
        report.stories_created += 1

    service = judge_service or JudgeService(settings, db, api_judge=api_judge,
                                            local_judge=local_judge)
    judged, unscored = service.judge_pending()
    report.stories_judged = judged
    report.stories_unscored = unscored

    report.stories_ranked = _rank_all(db, settings)
    report.finished_at = datetime.now(timezone.utc)
    return report


def _rank_all(db: Database, settings: Settings) -> int:
    now = datetime.now(timezone.utc)
    ranked = 0
    for story in db.all_stories():
        row = db.latest_judge(story.id)
        if row is None or story.judge_status not in ("api", "local"):
            continue
        members = db.story_members(story.id)
        times = [m.published_at or m.fetched_at for m in members if
                 (m.published_at or m.fetched_at)]
        age_hours = max(0.0, (now - max(times)).total_seconds() / 3600) if times else 0.0
        priority = compute_priority(
            row.supply_chain_relevance, row.saudi_gcc_relevance, row.market_impact,
            row.novelty, n_sources=len(members),
            credibility=db.story_max_credibility(story.id),
            age_hours=age_hours, cfg=settings.rank)
        db.set_story_ranking(story_id=story.id, priority=priority,
                             band=band_for(priority, settings.rank),
                             category=row.suggested_category)
        ranked += 1
    return ranked
