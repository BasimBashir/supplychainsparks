"""Deduplication and clustering: URL keys, fuzzy titles, simhash bodies, union-find.

This is plumbing (spec: no regex decides *relevance*) — merging near-identical
stories is identity resolution, not editorial judgment.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from rapidfuzz import fuzz

from sparks.models import ItemRecord

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


def _shingles(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9؀-ۿ]+", text.lower())
    if len(words) <= SHINGLE_SIZE:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + SHINGLE_SIZE]) for i in range(len(words) - SHINGLE_SIZE + 1)}


def simhash(text: str | None) -> int:
    if not text:
        return 0
    votes = [0] * SIMHASH_BITS
    for shingle in _shingles(text):
        digest = hashlib.md5(shingle.encode("utf-8")).digest()
        h = int.from_bytes(digest[:8], "big")
        for b in range(SIMHASH_BITS):
            votes[b] += 1 if (h >> b) & 1 else -1
    out = 0
    for b in range(SIMHASH_BITS):
        if votes[b] > 0:
            out |= 1 << b
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


@dataclass
class ClusterDecision:
    primary_item_id: int
    member_item_ids: list[int] = field(default_factory=list)
    title: str = ""


def build_clusters(items: list[ItemRecord], window_days: int = 7,
                   title_threshold: int = 90, simhash_threshold: int = 3) -> list[ClusterDecision]:
    """Cluster items into stories via union-find. Edges (within time window):
    title token-set ratio >= title_threshold OR body simhash distance <= simhash_threshold."""
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    hashes = [simhash(it.extracted_text) for it in items]
    window = timedelta(days=window_days)
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            times = [t for t in (a.published_at or a.fetched_at,
                                 b.published_at or b.fetched_at) if t]
            if times and abs(times[0] - times[1]) > window:
                continue
            same_title = (a.title_key and b.title_key
                          and fuzz.token_set_ratio(a.title_key, b.title_key) >= title_threshold)
            close_body = hamming(hashes[i], hashes[j]) <= simhash_threshold
            if same_title or close_body:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for idx in range(len(items)):
        groups.setdefault(find(idx), []).append(idx)

    clusters: list[ClusterDecision] = []
    for members in groups.values():
        def sort_key(m: int) -> tuple:
            it = items[m]
            t = it.published_at or it.fetched_at
            return (t is not None, t or it.fetched_at, -it.id)
        primary = sorted(members, key=sort_key, reverse=True)[0]
        clusters.append(ClusterDecision(
            primary_item_id=items[primary].id,
            member_item_ids=[items[m].id for m in members],
            title=items[primary].title or items[primary].url,
        ))
    return clusters

