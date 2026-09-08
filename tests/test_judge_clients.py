import json

import httpx
import pytest
import respx

from sparks.config import ApiJudgeConfig, LocalJudgeConfig
from sparks.judge.api import ApiJudge
from sparks.judge.local import OllamaJudge
from sparks.judge.schema import JudgeError, StoryContext

CTX = StoryContext(title="Jeddah expansion", lead="Mawani announced works.",
                   body="Body text.", n_sources=2)

VALID = {
    "supply_chain_relevance": 9, "saudi_gcc_relevance": 10, "market_impact": 8,
    "novelty": 7, "rationale_supply_chain": "r", "rationale_saudi_gcc": "r",
    "rationale_market_impact": "r", "rationale_novelty": "r",
    "suggested_category": "ports-shipping", "gist": "Mawani expands Jeddah.",
}


def _chat_response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@respx.mock
def test_api_judge_parses_json_with_code_fences():
    fenced = "```json\n" + json.dumps(VALID) + "\n```"
    route = respx.post("https://api.example/v4/chat/completions").respond(
        200, json={"choices": [{"message": {"content": fenced}}]})
    judge = ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4",
                                    model="m", api_key="k"))
    out = judge.judge(CTX)
    assert out.market_impact == 8
    body = json.loads(route.calls.last.request.content.decode())
    assert body["model"] == "m" and body["messages"][0]["role"] == "system"
    assert route.calls.last.request.headers["authorization"] == "Bearer k"


@respx.mock
def test_api_judge_retries_once_on_invalid_then_succeeds():
    route = respx.post("https://api.example/v4/chat/completions")
    route.side_effect = [
        httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]}),
        httpx.Response(200, json=_chat_response(VALID)),
    ]
    out = ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                  api_key="k")).judge(CTX)
    assert out.supply_chain_relevance == 9 and route.call_count == 2


@respx.mock
def test_api_judge_raises_after_retry_exhausted():
    respx.post("https://api.example/v4/chat/completions").respond(
        200, json={"choices": [{"message": {"content": "still not json"}}]})
    with pytest.raises(JudgeError):
        ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                api_key="k")).judge(CTX)


@respx.mock
def test_api_judge_http_error_raises_judge_error():
    respx.post("https://api.example/v4/chat/completions").respond(401)
    with pytest.raises(JudgeError):
        ApiJudge(ApiJudgeConfig(base_url="https://api.example/v4", model="m",
                                api_key="bad")).judge(CTX)


@respx.mock
def test_ollama_judge_parses_content():
    respx.post("http://localhost:11434/api/chat").respond(
        200, json={"message": {"content": json.dumps(VALID)}})
    out = OllamaJudge(LocalJudgeConfig()).judge(CTX)
    assert out.suggested_category == "ports-shipping"
    req = json.loads(respx.calls.last.request.content.decode())
    assert req["model"] == "qwen2.5:3b" and req["format"] == "json"


@respx.mock
def test_ollama_judge_connection_error_raises():
    respx.post("http://localhost:11434/api/chat").mock(side_effect=httpx.ConnectError("no"))
    with pytest.raises(JudgeError):
        OllamaJudge(LocalJudgeConfig()).judge(CTX)
