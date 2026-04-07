from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent

# Repo root .env (shared with Trigger CLI) then backend/.env (overrides). Missing files are skipped.
_env_candidates = (_REPO_ROOT / ".env", _BACKEND_ROOT / ".env")
_env_files = tuple(str(p) for p in _env_candidates if p.is_file())


class Settings(BaseSettings):
    # Loads repository root .env then backend/.env when those files exist.
    model_config = SettingsConfigDict(
        env_file=_env_files if _env_files else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = _BACKEND_ROOT / "data"
    database_url: str = "sqlite+aiosqlite:///" + str(_BACKEND_ROOT / "data" / "app.db").replace(
        "\\", "/"
    )
    # If set, API enqueues jobs to Redis (Arq); run worker: `arq app.worker.WorkerSettings` from backend/.
    redis_url: Optional[str] = None
    # Optional: enqueue via Trigger.dev REST API (see docs/deploy.md). Requires REDIS_URL + relay secret.
    trigger_secret_key: Optional[str] = None  # TRIGGER_SECRET_KEY — tr_dev_… / tr_prod_…
    trigger_api_base: str = "https://api.trigger.dev"  # TRIGGER_API_BASE
    # Must match task id in trigger/postclipper.ts (TRIGGER_RELAY_TASK_ID).
    trigger_relay_task_id: str = "postclipper-relay"
    # Shared secret for POST /internal/trigger-dev/relay (POSTCLIPPER_EXECUTOR_SECRET).
    postclipper_executor_secret: Optional[str] = None
    # Full URL path for relay (must match POSTCLIPPER_RELAY_PATH in Trigger task .env).
    postclipper_relay_path: str = "/internal/trigger-dev/relay"
    # Slim website API containers: skip FFmpeg/ffprobe checks (video runs on worker only).
    api_skip_media_check: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    youtube_client_secrets_path: Optional[Path] = None
    youtube_token_path: Optional[Path] = None
    # YouTube: web client often hits SABR/403; cookies fix age-restricted / signed-in streams.
    ytdlp_cookies_from_browser: Optional[str] = None  # e.g. chrome, edge, firefox
    ytdlp_cookies_file: Optional[Path] = None  # Netscape cookies.txt
    # Absolute paths avoid relying on PATH (Cursor/uvicorn often inherit a stale PATH on Windows).
    ffmpeg_path: Optional[Path] = None
    ffprobe_path: Optional[Path] = None
    # Clip suggestion: heuristic (regex/density) or embeddings (sentence-transformers; see requirements-ml.txt).
    suggest_engine: str = "heuristic"
    sentence_transformer_model: str = "all-MiniLM-L6-v2"

    @field_validator("redis_url", "trigger_secret_key", "postclipper_executor_secret", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v: object) -> object:
        if v == "":
            return None
        return v

    @field_validator("trigger_relay_task_id", mode="before")
    @classmethod
    def _relay_task_id(cls, v: object) -> object:
        if v is None or v == "" or (isinstance(v, str) and not str(v).strip()):
            return "postclipper-relay"
        return v

    @field_validator("postclipper_relay_path", mode="before")
    @classmethod
    def _relay_path(cls, v: object) -> object:
        if v is None or v == "" or (isinstance(v, str) and not str(v).strip()):
            return "/internal/trigger-dev/relay"
        s = str(v).strip()
        return s if s.startswith("/") else f"/{s}"


settings = Settings()
