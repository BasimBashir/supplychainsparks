"""Web-search sources: a user-chosen topic -> DuckDuckGo News via the ddgs
library (github.com/deedy5/ddgs, MIT, no API key) — so search sources work in
local-only mode too. Ollama's search runs through its cloud, GLM's needs a key;
ddgs is the only keyless, account-free option."""
from __future__ import annotations

from datetime import datetime

from ddgs import DDGS

from sparks.models import FetchedEntry


def search_news(topic: str, max_results: int = 20) -> list[FetchedEntry]:
    """Query DuckDuckGo News for a topic -> entries with snippet as summary."""
    with DDGS() as ddgs:
        results = ddgs.news(topic, max_results=max_results)
    entries: list[FetchedEntry] = []
    for r in results or []:
        url, title = (r.get("url") or "").strip(), (r.get("title") or "").strip()
        if not url or not title:
            continue
        published = None
        date = r.get("date")
        if date:
            try:
                published = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
            except ValueError:
                pass
        entries.append(FetchedEntry(url=url, title=title, published_at=published,
                                    summary=(r.get("body") or "").strip() or None))
    return entries
