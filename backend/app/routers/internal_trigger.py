"""Authenticated relay: Trigger.dev task POSTs here to enqueue Arq jobs (Redis)."""
from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import settings
from app.queue_client import (
    ARQ_TASK_GENERATE_CLIPS_PIPELINE,
    ARQ_TASK_PUBLISH,
    ARQ_TASK_RENDER_DRAFTS,
    ARQ_TASK_SUGGEST_ALTERNATIVE,
    ARQ_TASK_SUGGEST_CLIPS,
    ARQ_TASK_TRANSCRIBE,
    ARQ_TASK_TWITCH_INGEST,
    ARQ_TASK_UPLOAD_INGEST,
    ARQ_TASK_YOUTUBE_INGEST,
)

_ALLOWED_JOB_NAMES = frozenset(
    {
        ARQ_TASK_YOUTUBE_INGEST,
        ARQ_TASK_TWITCH_INGEST,
        ARQ_TASK_UPLOAD_INGEST,
        ARQ_TASK_TRANSCRIBE,
        ARQ_TASK_SUGGEST_CLIPS,
        ARQ_TASK_RENDER_DRAFTS,
        ARQ_TASK_GENERATE_CLIPS_PIPELINE,
        ARQ_TASK_SUGGEST_ALTERNATIVE,
        ARQ_TASK_PUBLISH,
    }
)


class RelayBody(BaseModel):
    job_name: str
    args: list[Any] = Field(default_factory=list)


def _relay_route_parts() -> tuple[str, str]:
    """Split POSTCLIPPER_RELAY_PATH into APIRouter prefix and POST subpath."""
    full = settings.postclipper_relay_path.rstrip("/")
    segments = [p for p in full.split("/") if p]
    if not segments:
        return "", "/relay"
    *dirs, leaf = segments
    prefix = "/" + "/".join(dirs) if dirs else ""
    return prefix, f"/{leaf}"


_prefix, _suffix = _relay_route_parts()
router = APIRouter(prefix=_prefix, tags=["internal"])


@router.post(_suffix)
async def relay_enqueue(
    request: Request,
    body: RelayBody,
    x_postclipper_executor_secret: str | None = Header(default=None, alias="X-PostClipper-Executor-Secret"),
):
    expected = settings.postclipper_executor_secret
    if not expected:
        raise HTTPException(503, "Relay disabled (POSTCLIPPER_EXECUTOR_SECRET unset on API)")
    prov = x_postclipper_executor_secret or ""
    if len(prov) != len(expected) or not secrets.compare_digest(
        prov.encode("utf-8"),
        expected.encode("utf-8"),
    ):
        raise HTTPException(401, "Invalid executor secret")

    if body.job_name not in _ALLOWED_JOB_NAMES:
        raise HTTPException(400, "Unknown job_name")

    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        raise HTTPException(503, "Arq pool not configured; set REDIS_URL on API")

    await pool.enqueue_job(body.job_name, *body.args)
    return {"ok": True}
