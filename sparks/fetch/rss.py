"""RSS/Atom parsing via feedparser."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser

from sparks.models import FetchedEntry


def parse_feed(data: bytes | str, max_items: int = 50) -> list[FetchedEntry]:
    parsed = feedparser.parse(data)
    entries: list[FetchedEntry] = []
    for e in parsed.entries[:max_items]:
        published = None
        for attr in ("published_parsed", "updated_parsed"):
            st = getattr(e, attr, None)
            if st:
                published = datetime(*st[:6], tzinfo=timezone.utc)
                break
        entries.append(FetchedEntry(url=e.get("link", ""), title=e.get("title", ""),
                                    published_at=published))
    return entries


def google_news_query_url(query: str, language: str = "en") -> str:
    q = quote_plus(query)
    locale = {"en": ("en-US", "US:en")}.get(language, ("en-US", "US:en"))
    return (f"https://news.google.com/rss/search?q={q}"
            f"&hl={locale[0]}&gl=US&ceid={locale[1]}")
