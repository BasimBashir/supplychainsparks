from pathlib import Path

from sparks.extract import extract_article

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_body_and_counts_words():
    result = extract_article((FIXTURES / "article_good.html").read_text(encoding="utf-8"))
    assert result is not None
    assert result.word_count >= 150
    assert "Jeddah Islamic Port" in result.text
    assert "Copyright Example News" not in result.text


def test_short_page_returns_none():
    assert extract_article((FIXTURES / "article_short.html").read_text(encoding="utf-8")) is None


def test_garbage_returns_none():
    assert extract_article("<html><body></body></html>") is None
