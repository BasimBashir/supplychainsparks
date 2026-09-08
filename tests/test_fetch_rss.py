from datetime import timezone
from pathlib import Path

from sparks.fetch.rss import google_news_query_url, parse_feed

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_feed_basic():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes())
    assert len(entries) == 3
    first = entries[0]
    assert first.title.startswith("Saudi Ports Authority")
    assert first.url == "https://example.com/jeddah-terminal?utm_source=rss"
    assert first.published_at is not None
    assert first.published_at.tzinfo == timezone.utc


def test_parse_feed_missing_date_is_none():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes())
    assert entries[2].published_at is None


def test_parse_feed_caps_items():
    entries = parse_feed((FIXTURES / "rss_basic.xml").read_bytes(), max_items=2)
    assert len(entries) == 2


def test_parse_feed_google_news_shape():
    entries = parse_feed((FIXTURES / "rss_google_news.xml").read_bytes())
    assert entries[0].title.startswith("Maersk")
    assert "news.google.com" in entries[0].url


def test_google_news_query_url():
    url = google_news_query_url('"Saudi" "logistics"')
    assert url == ("https://news.google.com/rss/search?q=%22Saudi%22+%22logistics%22"
                   "&hl=en-US&gl=US&ceid=US:en")
