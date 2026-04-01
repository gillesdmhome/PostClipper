from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.bg_tasks import run_twitch_ingest, run_upload_ingest, run_youtube_ingest
from app.dependencies import get_db
from app.models import Job, SourceType
from app.schemas import TwitchIngest, YoutubeIngest
from app.services.ingest import ensure_dirs

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


@router.post("/youtube")
async def ingest_youtube(
    body: YoutubeIngest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.youtube.value, source_url=body.url)
    session.add(job)
    await session.flush()
    background_tasks.add_task(run_youtube_ingest, job.id, body.url)
    return {"job_id": job.id, "status": job.status}


@router.post("/twitch")
async def ingest_twitch(
    body: TwitchIngest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.twitch.value, source_url=body.url)
    session.add(job)
    await session.flush()
    background_tasks.add_task(run_twitch_ingest, job.id, body.url)
    return {"job_id": job.id, "status": job.status}


@router.post("/upload")
async def ingest_upload(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    job = Job(source_type=SourceType.upload.value, original_filename=file.filename)
    session.add(job)
    await session.flush()

    dirs = ensure_dirs(job.id)
    raw_name = Path(file.filename or "recording.mp4").name
    dest = dirs["raw"] / raw_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    background_tasks.add_task(run_upload_ingest, job.id, str(dest.resolve()))
    return {"job_id": job.id, "status": job.status}
