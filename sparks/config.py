"""Configuration loading: bundled defaults <- user yaml <- env vars."""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass, field
from typing import Any

import yaml

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUNDLED_SETTINGS = REPO_ROOT / "settings.yaml"


@dataclass
class FetchConfig:
    user_agent: str = "SupplyChainSparksBot/0.1"
    per_domain_delay_seconds: float = 3.0
    timeout_seconds: int = 20
    max_items_per_source: int = 50
    schedule_hours: float = 6.0


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class PublishConfig:
    repo_url: str = ""
    branch: str = "main"
    token: str = ""
    site_base_url: str = "https://supplychainsparks.com"


@dataclass
class ApiJudgeConfig:
    base_url: str = "https://openrouter.ai/api/v1"   # any OpenAI-compatible API
    model: str = "openrouter/auto"                    # any vendor/model on it
    api_key: str = ""


@dataclass
class LocalJudgeConfig:
    enabled: bool = True
    ollama_url: str = "http://localhost:11434"
    model: str = "qwen2.5:3b"


@dataclass
class JudgeConfig:
    default_tier: str = "api"
    api: ApiJudgeConfig = field(default_factory=ApiJudgeConfig)
    local: LocalJudgeConfig = field(default_factory=LocalJudgeConfig)


@dataclass
class RankWeights:
    sc: float = 0.35
    saudi: float = 0.30
    impact: float = 0.25
    novelty: float = 0.10


@dataclass
class RankConfig:
    weights: RankWeights = field(default_factory=RankWeights)
    rubric_scale: float = 7.0
    corroboration_points: float = 4.0
    corroboration_cap: int = 3
    credibility_points: float = 6.0
    recency_points: float = 12.0
    recency_halflife_hours: float = 24.0
    high_band: float = 75.0
    medium_band: float = 50.0


@dataclass
class Settings:
    settings_path: pathlib.Path
    data_dir: pathlib.Path
    prompts_dir: pathlib.Path | None = None
    fetch: FetchConfig = field(default_factory=FetchConfig)
    judge: JudgeConfig = field(default_factory=JudgeConfig)
    rank: RankConfig = field(default_factory=RankConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    publish: PublishConfig = field(default_factory=PublishConfig)

    @property
    def db_path(self) -> pathlib.Path:
        return self.data_dir / "SupplyChainSparks.db"

    @property
    def raw_dir(self) -> pathlib.Path:
        return self.data_dir / "raw"


def _resolve_env(value: Any) -> Any:
    """Resolve strings of the form 'env:VARNAME' from the environment."""
    if isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], "")
    return value


def _merge(dataclass_obj: Any, data: dict) -> None:
    for key, value in data.items():
        value = _resolve_env(value)
        current = getattr(dataclass_obj, key)
        if hasattr(current, "__dataclass_fields__") and isinstance(value, dict):
            _merge(current, value)
        else:
            setattr(dataclass_obj, key, value)


def _default_data_dir() -> pathlib.Path:
    if os.name == "nt":
        local_app_data = os.environ.get("LOCALAPPDATA") or str(
            pathlib.Path.home() / "AppData" / "Local")
        return pathlib.Path(local_app_data) / "SupplyChainSparks"
    return pathlib.Path.home() / ".local" / "share" / "supplychainsparks"


def secrets_path(data_dir) -> pathlib.Path:
    """Secrets live in the user data dir (writable when installed, survives
    app updates) — never next to the exe or inside the build output."""
    return pathlib.Path(data_dir) / "secrets.yaml"


def read_secrets(data_dir) -> dict:
    import yaml
    path = secrets_path(data_dir)
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_secrets(data_dir, values: dict) -> None:
    import yaml
    path = secrets_path(data_dir)
    data: dict = read_secrets(data_dir)
    data.update({k: v for k, v in values.items() if v is not None})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def _migrate_legacy_secrets(settings_path, data_dir) -> dict:
    """Pre-2026-09 builds stored secrets.yaml next to the settings file (the
    bundled settings.yaml dir — wiped on every reinstall and read-only under
    Program Files). Move them to the data dir once."""
    legacy = pathlib.Path(settings_path).parent / "secrets.yaml"
    if not legacy.exists():
        return {}
    secrets = yaml.safe_load(legacy.read_text(encoding="utf-8")) or {}
    if secrets:
        write_secrets(data_dir, secrets)
    legacy.unlink()
    return secrets


def load_settings(path: pathlib.Path | str | None = None) -> Settings:
    if path is None:
        env_path = os.environ.get("SPARKS_SETTINGS")
        path = pathlib.Path(env_path) if env_path else BUNDLED_SETTINGS
    path = pathlib.Path(path)
    if not path.exists():
        raise FileNotFoundError(f"settings file not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    env_home = os.environ.get("SPARKS_HOME")
    data_dir = pathlib.Path(env_home) if env_home else _default_data_dir()

    prompts_dir = raw.get("prompts_dir")
    settings = Settings(
        settings_path=path,
        data_dir=data_dir,
        prompts_dir=pathlib.Path(prompts_dir) if prompts_dir else None,
    )
    if isinstance(raw.get("fetch"), dict):
        _merge(settings.fetch, raw["fetch"])
    if isinstance(raw.get("judge"), dict):
        _merge(settings.judge, raw["judge"])
    if isinstance(raw.get("rank"), dict):
        _merge(settings.rank, raw["rank"])
    if isinstance(raw.get("server"), dict):
        _merge(settings.server, raw["server"])
    if isinstance(raw.get("publish"), dict):
        _merge(settings.publish, raw["publish"])

    secrets = read_secrets(data_dir)
    if not secrets:
        secrets = _migrate_legacy_secrets(path, data_dir)
    if secrets.get("api_key"):
        settings.judge.api.api_key = secrets["api_key"]
    if secrets.get("repo_url"):
        settings.publish.repo_url = secrets["repo_url"]
    if secrets.get("git_token"):
        settings.publish.token = secrets["git_token"]
    if secrets.get("default_tier") in ("api", "local"):
        settings.judge.default_tier = secrets["default_tier"]
    if secrets.get("api_model"):
        settings.judge.api.model = secrets["api_model"]
    if secrets.get("api_base_url"):
        settings.judge.api.base_url = secrets["api_base_url"]
    if secrets.get("local_model"):
        settings.judge.local.model = secrets["local_model"]
    if secrets.get("schedule_hours") is not None:
        try:
            settings.fetch.schedule_hours = float(secrets["schedule_hours"])
        except (TypeError, ValueError):
            pass
    return settings
