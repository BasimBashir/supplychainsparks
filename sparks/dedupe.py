"""Deduplication and clustering: URL keys, fuzzy titles, simhash bodies, union-find.

This is plumbing (spec: no regex decides *relevance*) — merging near-identical
stories is identity resolution, not editorial judgment.

Task 2 scope: URL/title keys only. Task 6 adds simhash + build_clusters.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_", "ref", "igshid")
TITLE_DROP = re.compile(r"[^a-z0-9؀-ۿ]+")
SHINGLE_SIZE = 4
SIMHASH_BITS = 64


def normalize_url(url: str) -> str:
    s = urlsplit(url.strip().lower())
    query = sorted((k, v) for k, v in parse_qsl(s.query)
                   if not any(k.startswith(p) for p in TRACKING_PREFIXES))
    return urlunsplit((s.scheme, s.netloc, s.path.rstrip("/"), urlencode(query), ""))


def title_key(title: str | None) -> str | None:
    if not title:
        return None
    return " ".join(TITLE_DROP.split(title.lower())).strip() or None
