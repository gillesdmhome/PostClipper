from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.bg_tasks import run_publish, run_regenerate_caption, run_suggest_alternative
from app.config import settings
from app.dependencies import get_db
from app.models import ClipCandidate
from app.queue_client import (
    ARQ_TASK_PUBLISH,
    ARQ_TASK_REGENERATE_CAPTION,
    ARQ_TASK_SUGGEST_ALTERNATIVE,
    enqueue_task,
)
from app.schemas import CandidatePatch, PublishRequest

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


def _safe_under_data(abs_path: Path) -> bool:
    try:
        abs_path.resolve().relative_to(settings.data_dir.resolve())
        return True
    except ValueError:
        return False


@router.patch("/{candidate_id}")
async def patch_candidate(
    candidate_id: str,
    body: CandidatePatch,
    session: AsyncSession = Depends(get_db),
):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    if body.start_sec is not None:
        c.start_sec = body.start_sec
    if body.end_sec is not None:
        c.end_sec = body.end_sec
    if body.hook_text is not None:
        c.hook_text = body.hook_text
    if body.suggested_title is not None:
        c.suggested_title = body.suggested_title
    if body.suggested_hashtags is not None:
        c.suggested_hashtags = body.suggested_hashtags
    if body.suggested_description is not None:
        c.suggested_description = body.suggested_description
    if body.approved is not None:
        c.approved = body.approved
    if body.review_status is not None:
        c.review_status = body.review_status
    await session.flush()
    return {"ok": True, "id": candidate_id}


@router.post("/{candidate_id}/accept")
async def accept_candidate(candidate_id: str, session: AsyncSession = Depends(get_db)):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.review_status = "accepted"
    c.approved = 1
    await session.flush()
    return {"ok": True, "id": candidate_id, "review_status": "accepted"}


@router.post("/{candidate_id}/reject")
async def reject_candidate(candidate_id: str, session: AsyncSession = Depends(get_db)):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    c.review_status = "rejected"
    await session.flush()
    return {"ok": True, "id": candidate_id, "review_status": "rejected"}


@router.post("/{candidate_id}/suggest-alternative")
async def suggest_alternative(
    request: Request,
    candidate_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_SUGGEST_ALTERNATIVE,
        run_suggest_alternative,
        candidate_id,
    )
    return {
        "ok": True,
        "candidate_id": candidate_id,
        "message": "Queued: reject this clip and find a non-overlapping alternative + render",
    }


@router.post("/{candidate_id}/publish")
async def publish_candidate(
    request: Request,
    candidate_id: str,
    body: PublishRequest,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_PUBLISH,
        run_publish,
        candidate_id,
        body.platform,
        body.title,
        body.description,
    )
    return {"ok": True, "candidate_id": candidate_id, "platform": body.platform}


@router.post("/{candidate_id}/regenerate-caption")
async def regenerate_caption(
    request: Request,
    candidate_id: str,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
):
    c = await session.get(ClipCandidate, candidate_id)
    if not c:
        raise HTTPException(404, "Candidate not found")
    await enqueue_task(
        request,
        background_tasks,
        ARQ_TASK_REGENERATE_CAPTION,
        run_regenerate_caption,
        candidate_id,
    )
    return {"ok": True, "candidate_id": candidate_id, "message": "Queued: regenerate caption + re-render draft"}


@router.get("/{candidate_id}/media/draft")
async def draft_media(candidate_id: str, session: AsyncSession = Depends(get_db)):
    c = await session.get(ClipCandidate, candidate_id)
    if not c or not c.draft_video_path:
        raise HTTPException(404, "Draft video not available")
    p = Path(c.draft_video_path)
    if not p.is_file() or not _safe_under_data(p):
        raise HTTPException(404, "File missing")
    return FileResponse(p, media_type="video/mp4")
