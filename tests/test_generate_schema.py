import pytest
from pydantic import ValidationError

from sparks.generate.schema import GeneratedArticle, LinkedInPost, SeoBlock


def test_article_to_markdown():
    art = GeneratedArticle(headline="Jeddah capacity push", summary="Two million TEU added.",
                           what_happened="Works begin this quarter.",
                           why_it_matters="Strengthens the western corridor.",
                           takeaways=["Capacity: +2m TEU", "Timeline: 18 months"])
    md = art.to_markdown()
    assert md.startswith("Jeddah capacity push") and "## " in md
    assert "- Capacity: +2m TEU" in md
    assert "http" not in md


def test_linkedin_to_text_shape():
    post = LinkedInPost(hook="Big port news.", insights=["One.", "Two."],
                        cta="What does this mean for regional transshipment?",
                        hashtags=["supplychain", "saudiarabia"])
    text = post.to_text()
    assert text.split("\n\n")[0] == "Big port news."
    assert text.rstrip().endswith("#supplychain #saudiarabia")
    assert len(text) <= 1300


def test_missing_fields_rejected():
    with pytest.raises(ValidationError):
        LinkedInPost(hook="only hook")
