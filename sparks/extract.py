"""Article extraction via trafilatura + mechanical noise filter."""
from __future__ import annotations

from dataclasses import dataclass

import trafilatura

MIN_WORDS = 150  # spec 4.2: discard non-articles below this


@dataclass
class ExtractedText:
    text: str
    word_count: int
    language: str | None = None


def extract_article(html_text: str) -> ExtractedText | None:
    text = trafilatura.extract(html_text, include_comments=False,
                               include_tables=True, favor_recall=True)
    if not text:
        return None
    word_count = len(text.split())
    if word_count < MIN_WORDS:
        return None
    return ExtractedText(text=text, word_count=word_count, language=None)
