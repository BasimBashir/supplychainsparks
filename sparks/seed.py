"""Seed default sources — shared by `sparks init` and first app run.

A packaged install never runs the CLI, so the desktop app seeds the bundled
sources.yaml into its (empty) database on first launch; without this the fetch
cycle is a silent no-op."""
from __future__ import annotations

import pathlib

import yaml

from sparks.config import REPO_ROOT
from sparks.db import Database
from sparks.models import Source

SOURCES_SEED = REPO_ROOT / "sources.yaml"


def seed_sources(db: Database, seed_path: pathlib.Path = SOURCES_SEED) -> int:
    """Upsert every source in the yaml file. Returns how many were seeded."""
    data = yaml.safe_load(seed_path.read_text(encoding="utf-8")) or {}
    count = 0
    for raw in data.get("sources", []):
        db.upsert_source(Source(name=raw["name"], kind=raw["kind"], url=raw["url"],
                                credibility=float(raw.get("credibility", 0.5)),
                                category_hint=raw.get("category_hint"),
                                link_pattern=raw.get("link_pattern")))
        count += 1
    return count


def ensure_seeded(db: Database, seed_path: pathlib.Path = SOURCES_SEED) -> int:
    """Seed defaults only when the db has no sources at all (fresh install).

    Returns count seeded (0 when sources already exist — user config wins)."""
    if db.all_sources(enabled_only=False):
        return 0
    return seed_sources(db, seed_path)
