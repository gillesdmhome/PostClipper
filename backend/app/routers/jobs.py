from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bg_tasks import (
    run_generate_clips_pipeline,
    run_render_drafts,
    run_suggest_clips,
    run_transcribe,
)
from app.config import settings
from app.dependencies import get_db
from app.models import ClipCandidate, Job, JobLog, Transcript
from app.queue_client import (
    ARQ_TASK_GENERATE_CLIPS_PIPELINE,
    ARQ_TASK_RENDER_DRAFTS,
    ARQ_TASK_SUGGEST_CLIPS,
    ARQ_TASK_TRANSCRIBE,
    enqueue_task,
)
from app.schemas import ClipCandidateOut, JobDetail, JobLogOut, JobSummary, TranscriptOut

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _safe_under_data(abs_path: Path) -> bool:
    try:
        abs_path.resolve().relative_to(settings.data_dir.resolve())
        return True
    except ValueError:
        return False


@router.get("/dashboard")
async def dashboard(session: AsyncSession = Depends(get_db)):
    total = await session.scalar(select(func.count()).select_from(Job))
    failed = await session.scalar(select(func.count()).select_from(Job).where(Job.status == "failed"))
    by_status_rows = await session.execute(select(Job.status, func.count()).group_by(Job.status))
    by_status = {row[0]: row[1] for row in by_status_rows.all()}
    recent_q = await session.execute(select(Job).order_by(Job.created_at.desc()).limit(10))
    recent = [
        JobSummary.model_validate(j).model_dump()
        for j in recent_q.scalars().all()
    ]
    return {
        "total_jobs": total or 0,
        "failed_jobs": failed or 0,
        "by_status": by_status,
        "recent_jobs": recent,
    }


@router.get("", response_model=list[JobSummary])
async def list_jobs(session: AsyncSession = Depends(get_db)):
    q = await session.execute(select(Job).order_by(Job.created_at.desc()).limit(100))
    return list(q.scalars().all())


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, session: AsyncSession = Depends(get_db)):
    q = await session.execute(
        select(Job)
        .where(Job.id == job_id)
        .options(
            selectinload(Job.transcript).selectinload(Transcript.segments),
            selectinload(Job.candidates).selectinload(ClipCandidate.publish_jobs),
            selectinload(Job.ingest_logs),
        )
    )
    job = q.scalar_one_or_none()
    if not job:
        raise HTTPException(404, "Job not found")

    transcript_out = TranscriptOut.model_validate(job.transcript) if job.transcript else None

    logs_sorted = sorted(job.ingest_logs, key=lambda x: x.created_at)[-200:]
    cand_sorted = sorted(
        job.candidates,
        key=lambda x: (x.score if x.score is not None else -1e9),
        reverse=True,
    )

    return JobDetail(
        job=JobSummary.model_validate(job),
        transcript=transcript_out,
        candidates=[ClipCandidateOut.model_validate(c) for c in cand_sorted],
        logs=[JobLogOut.model_validate(l) for l in logs_sorted],
    )


@router.post("/{job_id}/generate-clips")
async def generate_clips_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    """
    Single action after ingest: transcribe (if not done), suggest clip candidates, render vertical drafts.
    This is the main workflow — call this when you want suggested clips; the rest runs automatically.
    """
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.mezzanine_path:
        raise HTTPException(400, "Ingest not finished — wait for mezzanine")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_GENERATE_CLIPS_PIPELINE,
        run_generate_clips_pipeline,
        job_id,
    )
    return {
        "ok": True,
        "job_id": job_id,
        "message": "Queued: transcribe (if needed) → suggest clips → render drafts",
    }


@router.post("/{job_id}/transcribe")
async def transcribe_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.mezzanine_path:
        raise HTTPException(400, "Mezzanine not ready")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_TRANSCRIBE,
        run_transcribe,
        job_id,
    )
    return {"ok": True, "job_id": job_id}


@router.post("/{job_id}/suggest-clips")
async def suggest_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_SUGGEST_CLIPS,
        run_suggest_clips,
        job_id,
    )
    return {"ok": True, "job_id": job_id}


@router.post("/{job_id}/render")
async def render_job(
    request: Request,
    job_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    job = await session.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_RENDER_DRAFTS,
        run_render_drafts,
        job_id,
    )
    return {"ok": True, "job_id": job_id}


@router.get("/{job_id}/media/proxy")
async def proxy_media(job_id: str, session: AsyncSession = Depends(get_db)):
    job = await session.get(Job, job_id)
    if not job or not job.proxy_path:
        raise HTTPException(404, "Proxy not available")
    p = Path(job.proxy_path)
    if not p.is_file() or not _safe_under_data(p):
        raise HTTPException(404, "File missing")
    return FileResponse(p, media_type="video/mp4")


@router.get("/{job_id}/media/mezzanine")
async def mezzanine_media(job_id: str, session: AsyncSession = Depends(get_db)):
    job = await session.get(Job, job_id)
    if not job or not job.mezzanine_path:
        raise HTTPException(404, "Mezzanine not available")
    p = Path(job.mezzanine_path)
    if not p.is_file() or not _safe_under_data(p):
        raise HTTPException(404, "File missing")
    return FileResponse(p, media_type="video/mp4")
