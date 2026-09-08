"""sparks CLI: init | fetch | queue | replay | sources."""
from __future__ import annotations

import argparse
import pathlib
import sys

import yaml

from sparks.config import REPO_ROOT, Settings, load_settings
from sparks.db import Database
from sparks.models import CycleReport, Source
from sparks.pipeline import replay, run_cycle

SOURCES_SEED = REPO_ROOT / "sources.yaml"


def _db(settings: Settings) -> Database:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return Database(settings.db_path)


def cmd_init(args, settings: Settings) -> int:
    db = _db(settings)
    data = yaml.safe_load(SOURCES_SEED.read_text(encoding="utf-8")) or {}
    count = 0
    for raw in data.get("sources", []):
        db.upsert_source(Source(name=raw["name"], kind=raw["kind"], url=raw["url"],
                                credibility=float(raw.get("credibility", 0.5)),
                                category_hint=raw.get("category_hint"),
                                link_pattern=raw.get("link_pattern")))
        count += 1
    print(f"seeded {count} sources from {SOURCES_SEED}")
    return 0


def cmd_fetch(args, settings: Settings) -> int:
    report: CycleReport = run_cycle(settings)
    errors = f" errors={len(report.errors)}" if report.errors else ""
    print(f"fetch done: items_new={report.items_new} "
          f"stories_created={report.stories_created} "
          f"stories_judged={report.stories_judged} "
          f"stories_ranked={report.stories_ranked}{errors}")
    for err in report.errors:
        print(f"  error: {err}", file=sys.stderr)
    return 1 if report.errors else 0


def cmd_queue(args, settings: Settings) -> int:
    db = _db(settings)
    stories = db.queue_stories(limit=args.n, band=args.band)
    if not stories:
        print("queue is empty — run `sparks fetch` first")
        return 0
    for s in stories:
        print(f"{s.band.upper():6} {s.priority:5.1f}  {s.category or '-':20} "
              f"{s.title}  ({s.n_sources} sources)")
    return 0


def cmd_replay(args, settings: Settings) -> int:
    report = replay(settings, skip_judge=args.skip_judge)
    print(f"replay done: stories_created={report.stories_created} "
          f"stories_ranked={report.stories_ranked} "
          f"stories_judged={report.stories_judged}")
    return 0


def cmd_sources(args, settings: Settings) -> int:
    db = _db(settings)
    if args.sources_cmd == "add":
        db.upsert_source(Source(name=args.name, kind=args.kind, url=args.url,
                                credibility=args.credibility,
                                category_hint=args.category_hint,
                                link_pattern=args.link_pattern))
        print(f"added source {args.name}")
    else:
        for s in db.all_sources(enabled_only=False):
            health = "ok" if s.healthy else "unhealthy"
            print(f"{s.kind:5} {health:10} cred={s.credibility:.1f}  {s.name}  {s.url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sparks")
    parser.add_argument("--settings", default=None, help="path to settings.yaml")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("fetch")
    q = sub.add_parser("queue")
    q.add_argument("-n", type=int, default=50)
    q.add_argument("--band", choices=["high", "medium", "low"], default=None)
    r = sub.add_parser("replay")
    r.add_argument("--skip-judge", action="store_true")
    s = sub.add_parser("sources")
    s_sub = s.add_subparsers(dest="sources_cmd", required=True)
    s_sub.add_parser("list")
    a = s_sub.add_parser("add")
    a.add_argument("--kind", choices=["rss", "html"], required=True)
    a.add_argument("--name", required=True)
    a.add_argument("--url", required=True)
    a.add_argument("--credibility", type=float, default=0.5)
    a.add_argument("--category-hint", default=None)
    a.add_argument("--link-pattern", default=None)

    args = parser.parse_args(argv)
    settings = load_settings(pathlib.Path(args.settings) if args.settings else None)
    handlers = {"init": cmd_init, "fetch": cmd_fetch, "queue": cmd_queue,
                "replay": cmd_replay, "sources": cmd_sources}
    return handlers[args.cmd](args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
