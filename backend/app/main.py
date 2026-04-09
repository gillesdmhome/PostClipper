from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import candidates, ingest, internal_trigger, jobs, publish
from app.services.ffmpeg_util import FFMPEG_SETUP_HINT, resolve_ffmpeg_ffprobe

_log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if sys.version_info < (3, 10):
        _log.warning(
            "Python %s is below 3.10; yt-dlp and other tools may warn or break. "
            "Install Python 3.10+ and recreate your venv.",
            sys.version.split()[0],
        )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    (settings.data_dir / "jobs").mkdir(parents=True, exist_ok=True)
    if settings.api_skip_media_check:
        _log.info("API_SKIP_MEDIA_CHECK: skipping FFmpeg discovery (use video worker for media).")
    else:
        ff, fp = resolve_ffmpeg_ffprobe()
        if ff and fp:
            _log.info("FFmpeg for ingest/render: %s", ff)
        else:
            _log.warning(
                "FFmpeg/ffprobe not resolved; YouTube merge and transcoding may fail. %s",
                FFMPEG_SETUP_HINT,
            )
    await init_db()
    pool = None
    if settings.redis_url:
        pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    app.state.arq_pool = pool
    if settings.trigger_secret_key and not settings.postclipper_executor_secret:
        _log.warning(
            "TRIGGER_SECRET_KEY is set but POSTCLIPPER_EXECUTOR_SECRET is unset; "
            "relay route is disabled and Trigger runs will fail until the secret is configured."
        )
    try:
        yield
    finally:
        if pool is not None:
            await pool.close()


app = FastAPI(title="Clip Social Pipeline", lifespan=lifespan)

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router)
if settings.postclipper_executor_secret:
    app.include_router(internal_trigger.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(publish.router)


@app.get("/health")
async def health(request: Request):
    if settings.api_skip_media_check:
        return {
            "status": "ok",
            "media_check_skipped": True,
            "ffmpeg_ok": None,
            "ffmpeg": None,
            "ffprobe": None,
            "job_queue": _job_queue_label(getattr(request.app.state, "arq_pool", None)),
        }
    ff, fp = resolve_ffmpeg_ffprobe()
    return {
        "status": "ok",
        "media_check_skipped": False,
        "ffmpeg_ok": bool(ff and fp),
        "ffmpeg": ff,
        "ffprobe": fp,
        "job_queue": _job_queue_label(getattr(request.app.state, "arq_pool", None)),
    }


def _job_queue_label(pool) -> str:
    if settings.trigger_secret_key:
        return "trigger_dev"
    return "redis" if pool is not None else "in_process"
