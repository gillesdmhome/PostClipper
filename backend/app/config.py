from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Always load backend/.env, not cwd-relative (uvicorn started from repo root would miss FFMPEG_PATH).
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = _BACKEND_ROOT / "data"
    database_url: str = "sqlite+aiosqlite:///" + str(_BACKEND_ROOT / "data" / "app.db").replace(
        "\\", "/"
    )
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


settings = Settings()
