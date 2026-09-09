import httpx
import pytest
from fastapi.testclient import TestClient

from sparks.db import Database
from sparks.server.app import create_app


@pytest.fixture
def env(settings):
    db = Database(settings.db_path)
    tc = TestClient(create_app(settings, db=db))
    return tc, {"X-Sparks-Token": db.get_setting("server_token")}, settings


def test_settings_status_defaults(env):
    tc, h, settings = env
    r = tc.get("/api/settings-status", headers=h)
    assert r.status_code == 200
    data = r.json()
    assert data["has_api_key"] is False and data["has_repo"] is False
    assert data["schedule_hours"] == 6


def test_settings_status_ollama_detected(env, monkeypatch):
    tc, h, settings = env
    monkeypatch.setattr(httpx, "get",
                        lambda url, **kw: type("R", (), {"status_code": 200})())
    assert tc.get("/api/settings-status", headers=h).json()["ollama"] is True


def test_post_settings_persists_secrets(env):
    tc, h, settings = env
    r = tc.post("/api/settings", headers=h,
                json={"api_key": "sk-new", "repo_url": "https://github.com/o/r.git",
                      "git_token": "gt", "schedule_hours": 4})
    assert r.status_code == 200
    secrets_file = settings.settings_path.parent / "secrets.yaml"
    text = secrets_file.read_text(encoding="utf-8")
    assert "sk-new" in text and "github.com/o/r" in text


def test_post_settings_persists_tier_and_models(env):
    tc, h, settings = env
    r = tc.post("/api/settings", headers=h,
                json={"default_tier": "local", "api_model": "glm-4-plus",
                      "local_model": "qwen2.5:7b"})
    assert r.status_code == 200
    from sparks.config import load_settings
    reloaded = load_settings(settings.settings_path)
    assert reloaded.judge.default_tier == "local"
    assert reloaded.judge.api.model == "glm-4-plus"
    assert reloaded.judge.local.model == "qwen2.5:7b"


def test_settings_status_reports_tier_and_models(env):
    tc, h, settings = env
    data = tc.get("/api/settings-status", headers=h).json()
    assert data["default_tier"] == "local"  # conftest fixture sets local
    assert data["api_model"] and data["local_model"]
