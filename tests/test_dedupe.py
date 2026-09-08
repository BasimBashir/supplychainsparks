from datetime import datetime, timedelta, timezone
from pathlib import Path

from sparks.dedupe import build_clusters, hamming, normalize_url, simhash, title_key
from sparks.extract import extract_article
from sparks.models import ItemRecord

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 9, 8, 10, 0, tzinfo=timezone.utc)


def item(iid, title, text=None, published=NOW, url=None):
    return ItemRecord(id=iid, source_id=1, url=url or f"https://x.com/{iid}",
                      url_key=normalize_url(url or f"https://x.com/{iid}"),
                      title=title, title_key=title_key(title), published_at=published,
                      fetched_at=NOW, raw_path="", extracted_text=text)


def test_normalize_url_strips_tracking_and_normalizes():
    assert normalize_url("https://Example.com/story/?utm_source=rss&fbclid=abc&id=2") == \
           normalize_url("https://example.com/story?id=2")
    assert normalize_url("https://example.com/story") == normalize_url("https://example.com/story/")
    assert normalize_url("https://example.com/a?utm_campaign=x") == "https://example.com/a"


def test_title_key_collapses_case_and_punctuation():
    assert title_key("Red-Sea Shipping: Update!") == title_key("red sea shipping update")


def test_simhash_near_identical_texts_are_close():
    a = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8")).text
    b = extract_article((FIXTURES / "article_variant.html").read_text(encoding="utf-8")).text
    # lightly-edited variant: much closer than an unrelated text
    assert hamming(simhash(a), simhash(b)) <= 12
    other = "Rainfall disrupted railway timetables across northern Europe yesterday " * 10
    assert hamming(simhash(a), simhash(other)) > 20


def test_build_clusters_merges_same_title_and_similar_body():
    a = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8")).text
    b = extract_article((FIXTURES / "article_variant.html").read_text(encoding="utf-8")).text
    items = [
        item(1, "Saudi Ports Authority announces new container terminal at Jeddah", a),
        item(2, "Saudi Ports Authority announces new container terminal at Jeddah!", b,
             url="https://y.com/2"),   # same title modulo punctuation + near-same body
        item(3, "Dammam warehouse district sees record occupancy", url="https://y.com/3"),
    ]
    clusters = build_clusters(items, window_days=7)
    assert len(clusters) == 2
    merged = max(clusters, key=lambda c: len(c.member_item_ids))
    assert {1, 2} <= set(merged.member_item_ids)
    assert 3 in [m for c in clusters for m in c.member_item_ids]


def test_build_clusters_respects_time_window():
    old = item(1, "Same headline story", published=NOW - timedelta(days=10))
    new = item(2, "Same headline story", published=NOW, url="https://y.com/2")
    clusters = build_clusters([old, new], window_days=7)
    assert len(clusters) == 2  # too far apart to merge


def test_build_clusters_picks_primary_by_recency_then_id():
    items = [item(5, "Headline A", published=NOW - timedelta(hours=2)),
             item(2, "Headline A", published=NOW, url="https://y.com/2")]
    clusters = build_clusters(items)
    assert clusters[0].primary_item_id == 2  # newest becomes primary
