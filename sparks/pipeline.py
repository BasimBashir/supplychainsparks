"""Pipeline orchestration: fetch -> content -> extract -> cluster -> judge -> rank."""
from __future__ import annotations

import pathlib
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


def replay(settings: Settings, db: Database | None = None, skip_judge: bool = False,
           api_judge=None, local_judge=None) -> CycleReport:
    """Rebuild stories/judgments/rankings from raw files with current config.

    Judge verdicts are cached by the primary item's url_key and restored when the
    same story re-clusters, so config iterations cost nothing. Missing verdicts are
    re-judged unless skip_judge=True."""
    db = db or Database(settings.db_path)
    report = CycleReport(started_at=datetime.now(timezone.utc))

    cache: dict[str, object] = {}
    for story in db.all_stories():
        row = db.latest_judge(story.id)
        if row is None:
            continue
        primary = next((m for m in db.story_members(story.id)
                        if m.id == story.primary_item_id), None)
        if primary:
            cache[primary.url_key] = row

    db.wipe_derived()

    from sparks.extract import extract_article
    for item in db.window_items(days=3650):
        try:
            html = pathlib.Path(item.raw_path).read_text(encoding="utf-8",
                                                         errors="replace")
            extracted = extract_article(html)
        except OSError:
            continue
        if extracted is not None:
            db.update_item_extraction(item.id, extracted.text, extracted.language,
                                      extracted.word_count)
        else:
            # search items keep their snippet when the page won't extract
            source = db.get_source(item.source_id)
            summary = (item.summary or "").split()
            if (source is not None and source.kind == "search"
                    and len(summary) >= 10):
                db.update_item_extraction(item.id, " ".join(summary), None,
                                          len(summary))

    all_items = db.window_items(days=3650)
    for cluster in build_clusters(all_items):
        story_id = db.create_story(title=cluster.title,
                                   primary_item_id=cluster.primary_item_id)
        for member_id in cluster.member_item_ids:
            db.assign_story(member_id, story_id)
        report.stories_created += 1
        primary = next(m for m in all_items if m.id == cluster.primary_item_id)
        cached = cache.get(primary.url_key)
        if cached is not None:
            db.save_judge_score(story_id, tier=cached.tier, model=cached.model,
                                prompt_version=cached.prompt_version, output=cached)
            db.set_story_judge_status(story_id, cached.tier)

    if not skip_judge:
        service = JudgeService(settings, db, api_judge=api_judge, local_judge=local_judge)
        judged, unscored = service.judge_pending()
        report.stories_judged, report.stories_unscored = judged, unscored

    report.stories_ranked = _rank_all(db, settings)
    report.finished_at = datetime.now(timezone.utc)
    return report
