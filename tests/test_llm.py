import json

import httpx
import pytest
import respx
from pydantic import BaseModel

from sparks.llm import LlmClient

PAYLOAD = {"slug": "jeddah-capacity", "description": "d", "tags": ["ports"]}


class Seo(BaseModel):
    slug: str
    description: str
    tags: list[str]


def _chat(payload):
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def test_api_tier_posts_to_chat_completions(settings):
    settings.judge.default_tier = "api"
    settings.judge.api.base_url = "https://api.example/v4"
    settings.judge.api.model = "qwen/qwen3-235b-a22b"
    settings.judge.api.api_key = "sk-test"
    with respx.mock:
        route = respx.post("https://api.example/v4/chat/completions").respond(
            200, json=_chat(PAYLOAD))
        out = LlmClient(settings).complete_json(
            [{"role": "user", "content": "hi"}], Seo)
    assert out.slug == "jeddah-capacity"
    body = json.loads(route.calls.last.request.content.decode())
    assert body["model"] == "qwen/qwen3-235b-a22b"
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-test"


def test_local_tier_posts_to_ollama_without_auth(settings):
    settings.judge.default_tier = "local"
    settings.judge.local.model = "qwen2.5:7b"
    with respx.mock:
        route = respx.post("http://localhost:11434/api/chat").respond(
            200, json={"message": {"content": json.dumps(PAYLOAD)}})
        out = LlmClient(settings).complete_json(
            [{"role": "user", "content": "hi"}], Seo)
    assert out.slug == "jeddah-capacity"
    body = json.loads(route.calls.last.request.content.decode())
    assert body["model"] == "qwen2.5:7b" and body["format"] == "json"
    assert "authorization" not in route.calls.last.request.headers


def test_local_tier_needs_no_api_key(settings):
    settings.judge.default_tier = "local"
    settings.judge.api.api_key = ""
    with respx.mock:
        respx.post("http://localhost:11434/api/chat").respond(
            200, json={"message": {"content": json.dumps(PAYLOAD)}})
        out = LlmClient(settings).complete_json([{"role": "user", "content": "x"}], Seo)
    assert out.tags == ["ports"]


def test_wraps_transport_errors(settings):
    settings.judge.default_tier = "api"
    settings.judge.api.base_url = "https://api.example/v4"
    with respx.mock:
        respx.post("https://api.example/v4/chat/completions").respond(500)
        with pytest.raises(Exception):
            LlmClient(settings).complete_json([{"role": "user", "content": "x"}], Seo)
