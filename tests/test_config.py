import pathlib

import pytest

from sparks.config import load_settings


def repo_settings_path():
    return pathlib.Path(__file__).parents[1] / "settings.yaml"


def test_defaults_from_bundled_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path))
    s = load_settings(repo_settings_path())
    assert s.fetch.per_domain_delay_seconds == 3
    assert s.judge.default_tier == "api"
    assert s.judge.local.model == "qwen2.5:3b"
    assert s.rank.weights.sc == pytest.approx(0.35)
    assert s.rank.high_band == 75.0
    assert s.db_path.parent == tmp_path


def test_user_yaml_overrides_defaults(settings):
    assert settings.judge.default_tier == "local"  # from conftest fixture yaml


def test_env_placeholder_resolves_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_TEST_KEY", "sk-test-123")
    p = tmp_path / "s.yaml"
    p.write_text("judge:\n  api:\n    api_key: env:SPARKS_TEST_KEY\n", encoding="utf-8")
    s = load_settings(p)
    assert s.judge.api.api_key == "sk-test-123"


def test_missing_settings_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.yaml")


def test_server_and_publish_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path))
    s = load_settings(repo_settings_path())
    assert s.server.host == "127.0.0.1" and s.server.port == 8765
    assert s.publish.branch == "main"
    assert s.fetch.schedule_hours == 0
