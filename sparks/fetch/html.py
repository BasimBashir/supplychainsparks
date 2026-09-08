"""Extract candidate article links from HTML listing pages (plumbing only)."""
from __future__ import annotations

import html as html_mod
import re
from urllib.parse import urljoin

from sparks.models import FetchedEntry

_ANCHOR_RE = re.compile(
    r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def parse_listing(html_text: str, base_url: str, link_pattern: str | None,
                  max_items: int = 50) -> list[FetchedEntry]:
    entries: list[FetchedEntry] = []
    seen: set[str] = set()
    for href, inner in _ANCHOR_RE.findall(html_text):
        absolute = urljoin(base_url, href.strip())
        if not absolute.startswith(("http://", "https://")):
            continue
        if absolute in seen:
            continue
        if link_pattern and not re.search(link_pattern, absolute):
            continue
        title = html_mod.unescape(_TAG_RE.sub("", inner)).strip()
        if not title:
            title = absolute.rsplit("/", 1)[-1].replace("-", " ").strip()
        seen.add(absolute)
        entries.append(FetchedEntry(url=absolute, title=title, published_at=None))
        if len(entries) >= max_items:
            break
    return entries
