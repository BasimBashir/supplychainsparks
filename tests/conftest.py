import pathlib

import pytest

from sparks.config import load_settings


@pytest.fixture
def settings_path(tmp_path, monkeypatch) -> pathlib.Path:
    """Point the engine at an isolated data dir + settings file."""
    path = tmp_path / "settings.yaml"
    path.write_text("judge:\n  default_tier: local\n", encoding="utf-8")
    monkeypatch.setenv("SPARKS_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("SPARKS_SETTINGS", str(path))
    return path


@pytest.fixture
def settings(settings_path):
    return load_settings(settings_path)
