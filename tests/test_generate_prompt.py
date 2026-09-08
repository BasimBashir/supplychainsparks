from sparks.generate.prompt import render_generation_prompt
from sparks.judge.schema import StoryContext


def test_article_en_prompt_has_constraints_and_context():
    ctx = StoryContext(title="Jeddah expansion", lead="Mawani announced works.",
                       body="Body.", n_sources=3)
    msgs = render_generation_prompt("article", "en", ctx)
    system = msgs[0]["content"]
    assert "Do NOT mention any publisher" in system
    assert "URLs" in system and "invent" in system.lower()
    assert "Jeddah expansion" in msgs[1]["content"]


def test_linkedin_ar_prompt_exists_and_mentions_arabic():
    msgs = render_generation_prompt("linkedin", "ar",
                                    StoryContext(title="t", lead="l", body="b", n_sources=1))
    assert "Arabic" in msgs[0]["content"] or "Arabic" in msgs[1]["content"]


def test_seo_prompt_renders():
    msgs = render_generation_prompt("seo", "en",
                                    StoryContext(title="t", lead="l", body="b", n_sources=1))
    assert "slug" in msgs[0]["content"]
