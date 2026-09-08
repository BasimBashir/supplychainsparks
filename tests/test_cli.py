import yaml
from datetime import datetime, timezone

from sparks.cli import main
from sparks.db import Database
from sparks.models import CycleReport, FetchedEntry, Source

NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def test_init_seeds_sources(settings, capsys):
    assert main(["init"]) == 0
    db = Database(settings.db_path)
    from sparks.cli import SOURCES_SEED
    expected = len(yaml.safe_load(SOURCES_SEED.read_text(encoding="utf-8"))["sources"])
    assert len(db.all_sources(enabled_only=False)) == expected
    assert "seeded" in capsys.readouterr().out


def test_sources_add_and_list(settings, capsys):
    assert main(["sources", "add", "--kind", "rss", "--name", "My Feed",
                 "--url", "https://my.example/rss", "--credibility", "0.7"]) == 0
    assert main(["sources", "list"]) == 0
    out = capsys.readouterr().out
    assert "My Feed" in out and "rss" in out


def test_queue_prints_ranked_stories(settings, capsys):
    db = Database(settings.db_path)
    sid = db.upsert_source(Source(name="S", kind="rss", url="https://s.com/rss"))
    iid = db.insert_item(sid, FetchedEntry("https://s.com/a", "Jeddah expansion", NOW),
                         "raw", NOW)
    story_id = db.create_story("Jeddah expansion", iid)
    db.set_story_judge_status(story_id, "api")
    db.set_story_ranking(story_id, 88.0, "high", "ports-shipping")
    db.close()
    assert main(["queue"]) == 0
    out = capsys.readouterr().out
    assert "Jeddah expansion" in out and "88" in out and "HIGH" in out


def test_fetch_invokes_pipeline(settings, capsys, monkeypatch):
    import sparks.cli as cli

    def fake_report():
        return CycleReport(started_at=NOW, finished_at=NOW, items_new=5,
                           stories_created=2, stories_judged=2, stories_ranked=2)

    monkeypatch.setattr(cli, "run_cycle", lambda s: fake_report())
    assert main(["fetch"]) == 0
    out = capsys.readouterr().out
    assert "items_new=5" in out and "stories_ranked=2" in out


def test_replay_invokes_pipeline(settings, capsys, monkeypatch):
    import sparks.cli as cli
    monkeypatch.setattr(cli, "replay",
                        lambda s, skip_judge=False: CycleReport(started_at=NOW))
    assert main(["replay", "--skip-judge"]) == 0
    assert "replay" in capsys.readouterr().out.lower()
