from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.routers import candidates, ingest, jobs, publish
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
    ff, fp = resolve_ffmpeg_ffprobe()
    if ff and fp:
        _log.info("FFmpeg for ingest/render: %s", ff)
    else:
        _log.warning(
            "FFmpeg/ffprobe not resolved; YouTube merge and transcoding may fail. %s",
            FFMPEG_SETUP_HINT,
        )
    await init_db()
    yield


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
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(publish.router)


@app.get("/health")
async def health():
    ff, fp = resolve_ffmpeg_ffprobe()
    return {
        "status": "ok",
        "ffmpeg_ok": bool(ff and fp),
        "ffmpeg": ff,
        "ffprobe": fp,
    }
