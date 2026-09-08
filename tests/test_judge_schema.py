import pytest
from pydantic import ValidationError

from sparks.judge.schema import CATEGORIES, PROMPT_VERSION, JudgeOutput, StoryContext


def make_output(**over):
    base = dict(
        supply_chain_relevance=8, saudi_gcc_relevance=9, market_impact=6, novelty=5,
        rationale_supply_chain="core logistics story", rationale_saudi_gcc="KSA port capex",
        rationale_market_impact="large capex", rationale_novelty="follows prior plan",
        suggested_category="ports-shipping", gist="Mawani expands Jeddah capacity.")
    base.update(over)
    return JudgeOutput(**base)


def test_valid_output_and_version():
    jo = make_output()
    assert 0 <= jo.market_impact <= 10
    assert jo.suggested_category in CATEGORIES
    assert PROMPT_VERSION == "judge_v1"


def test_out_of_range_rejected():
    with pytest.raises(ValidationError):
        make_output(market_impact=11)
    with pytest.raises(ValidationError):
        make_output(supply_chain_relevance=-1)


def test_unknown_category_normalized_to_other():
    assert make_output(suggested_category="totally-new-category").suggested_category == "other"


def test_story_context_holds_fields():
    ctx = StoryContext(title="T", lead="L", body="B", n_sources=3)
    assert ctx.n_sources == 3
