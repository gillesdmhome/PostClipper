from __future__ import annotations

"""
Ingest routes: URL ingests enqueue work on the video worker. File upload streams bytes
into DATA_DIR on this process — in split deploy, mount the same volume on API and worker
(see docs/deploy.md) so the worker can read raw uploads and write outputs.

Upload disk writes run in a thread pool so large files do not block the asyncio event loop
(other API routes like GET /api/jobs/{id} stay responsive during uploads).
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.bg_tasks import run_twitch_ingest, run_upload_ingest, run_youtube_ingest
from app.dependencies import get_db
from app.models import Job, SourceType
from app.queue_client import (
    ARQ_TASK_TWITCH_INGEST,
    ARQ_TASK_UPLOAD_INGEST,
    ARQ_TASK_YOUTUBE_INGEST,
    enqueue_task,
)
from app.schemas import TwitchIngest, YoutubeIngest
from app.services.ingest import ensure_dirs

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/youtube")
async def ingest_youtube(
    request: Request,
    body: YoutubeIngest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.youtube.value, source_url=body.url)
    session.add(job)
    await session.flush()
    await session.commit()
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_YOUTUBE_INGEST,
        run_youtube_ingest,
        job.id,
        body.url,
    )
    return {"job_id": job.id, "status": job.status}


@router.post("/twitch")
async def ingest_twitch(
    request: Request,
    body: TwitchIngest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.twitch.value, source_url=body.url)
    session.add(job)
    await session.flush()
    await session.commit()
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_TWITCH_INGEST,
        run_twitch_ingest,
        job.id,
        body.url,
    )
    return {"job_id": job.id, "status": job.status}


@router.post("/upload")
async def ingest_upload(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.upload.value, original_filename=file.filename)
    session.add(job)
    await session.flush()
    await session.commit()

    dirs = ensure_dirs(job.id)
    raw_name = Path(file.filename or "recording.mp4").name
    dest = dirs["raw"] / raw_name
    await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            await asyncio.to_thread(f.write, chunk)
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_UPLOAD_INGEST,
        run_upload_ingest,
        job.id,
        str(dest.resolve()),
    )
    return {"job_id": job.id, "status": job.status}
