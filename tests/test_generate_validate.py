from sparks.generate.validate import assert_publishable


def test_clean_text_passes():
    assert assert_publishable("Plain analysis text.", ["Reuters"]) == []


def test_urls_flagged():
    violations = assert_publishable("See https://example.com and www.news.com", [])
    assert len(violations) == 2


def test_blocked_source_names_flagged_case_insensitive():
    violations = assert_publishable("As reported by REUTERS today.", ["Reuters"])
    assert violations and "Reuters" in violations[0]
