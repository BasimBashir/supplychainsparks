from pathlib import Path

from sparks.fetch.html import parse_listing

HTML = (Path(__file__).parent / "fixtures" / "html_listing.html").read_text(encoding="utf-8")


def test_parse_listing_filters_by_pattern_and_resolves_relative():
    entries = parse_listing(HTML, base_url="https://mawani.example/en/media",
                            link_pattern="press-releases")
    urls = [e.url for e in entries]
    assert "https://mawani.example/press-releases/2026/mawani-new-berth" in urls
    assert "https://mawani.example/press-releases/2026/mawani-record-throughput" in urls
    assert all("/news/" not in u for u in urls)
    assert all(u.startswith("http") for u in urls)
    assert entries[0].title == "Mawani inaugurates new berth at Jeddah"


def test_parse_listing_no_pattern_returns_all_http_links():
    entries = parse_listing(HTML, base_url="https://mawani.example", link_pattern=None)
    assert len(entries) >= 4


def test_parse_listing_caps_items():
    entries = parse_listing(HTML, base_url="https://mawani.example", link_pattern=None,
                            max_items=2)
    assert len(entries) == 2
