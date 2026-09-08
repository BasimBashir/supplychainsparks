from sparks.judge.prompt import render_judge_prompt
from sparks.judge.schema import StoryContext


def test_prompt_contains_context_and_schema():
    ctx = StoryContext(title="Jeddah expansion", lead="Mawani announced capacity works.",
                       body="Body text here.", n_sources=4)
    messages = render_judge_prompt(ctx)
    assert messages[0]["role"] == "system"
    user = messages[1]["content"]
    assert "Jeddah expansion" in user and "Body text here." in user
    assert "4" in user
    for field in ("supply_chain_relevance", "rationale_market_impact", "suggested_category"):
        assert field in messages[0]["content"]


def test_prompt_anchor_examples_present():
    messages = render_judge_prompt(StoryContext("t", "l", "b", 1))
    assert "ANCHOR" in messages[0]["content"]


def test_prompt_override_dir_used(settings, tmp_path):
    override = tmp_path / "prompts" / "judge_v1.md"
    override.parent.mkdir(parents=True)
    override.write_text("OVERRIDE SYSTEM {{SCHEMA_FIELDS}}", encoding="utf-8")
    settings.prompts_dir = tmp_path / "prompts"
    from sparks.judge import prompt as prompt_mod
    messages = prompt_mod.render_judge_prompt(
        StoryContext("t", "l", "b", 1), settings=settings)
    assert messages[0]["content"] == "OVERRIDE SYSTEM supply_chain_relevance, saudi_gcc_relevance, market_impact, novelty, rationale_supply_chain, rationale_saudi_gcc, rationale_market_impact, rationale_novelty, suggested_category, gist"
