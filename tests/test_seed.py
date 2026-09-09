import yaml

from sparks.db import Database
from sparks.models import Source
from sparks.seed import SOURCES_SEED, ensure_seeded, seed_sources

YAML = """sources:
  - name: Reuters
    kind: rss
    url: https://r.com/rss
    credibility: 0.8
  - name: Aramco
    kind: html
    url: https://www.aramco.com/news
    link_pattern: press
"""


def _write_seed(tmp_path) -> object:
    path = tmp_path / "sources.yaml"
    path.write_text(YAML, encoding="utf-8")
    return path


def test_seed_sources_upserts_all(settings, tmp_path):
    db = Database(settings.db_path)
    count = seed_sources(db, _write_seed(tmp_path))
    assert count == 2
    names = {s.name for s in db.all_sources(enabled_only=False)}
    assert names == {"Reuters", "Aramco"}


def test_ensure_seeded_is_noop_when_sources_exist(settings, tmp_path):
    db = Database(settings.db_path)
    db.upsert_source(Source(name="Custom", kind="rss", url="https://c.com/rss"))
    assert ensure_seeded(db, _write_seed(tmp_path)) == 0
    assert len(db.all_sources(enabled_only=False)) == 1  # user sources untouched


def test_ensure_seeded_fresh_db_gets_defaults(settings, tmp_path):
    db = Database(settings.db_path)
    assert ensure_seeded(db, _write_seed(tmp_path)) == 2
    # second call: already seeded, nothing added
    assert ensure_seeded(db, _write_seed(tmp_path)) == 0
    assert len(db.all_sources(enabled_only=False)) == 2


def test_bundled_seed_file_is_valid(settings):
    """The packaged app seeds from SOURCES_SEED — it must parse and load."""
    data = yaml.safe_load(SOURCES_SEED.read_text(encoding="utf-8"))
    assert data and data.get("sources"), "sources.yaml must define sources"
    db = Database(settings.db_path)
    assert seed_sources(db, SOURCES_SEED) == len(data["sources"])
