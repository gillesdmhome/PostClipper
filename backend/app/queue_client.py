"""Enqueue long-running work: optional Trigger.dev → relay → Arq, else Redis (Arq), else BackgroundTasks."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import BackgroundTasks, Request

from app.config import settings

TaskFn = Callable[..., Awaitable[Any]]

# Must match coroutine __name__ entries in app.worker.WorkerSettings.functions
ARQ_TASK_YOUTUBE_INGEST = "task_youtube_ingest"
ARQ_TASK_TWITCH_INGEST = "task_twitch_ingest"
ARQ_TASK_UPLOAD_INGEST = "task_upload_ingest"
ARQ_TASK_TRANSCRIBE = "task_transcribe"
ARQ_TASK_SUGGEST_CLIPS = "task_suggest_clips"
ARQ_TASK_RENDER_DRAFTS = "task_render_drafts"
ARQ_TASK_GENERATE_CLIPS_PIPELINE = "task_generate_clips_pipeline"
ARQ_TASK_SUGGEST_ALTERNATIVE = "task_suggest_alternative"
ARQ_TASK_PUBLISH = "task_publish"


async def enqueue_task(
    request: Request,
    background_tasks: BackgroundTasks,
    arq_job_name: str,
    coro: TaskFn,
    *args: Any,
) -> None:
    pool = getattr(request.app.state, "arq_pool", None)
    if settings.trigger_secret_key:
        if pool is None:
            raise RuntimeError(
                "TRIGGER_SECRET_KEY is set but REDIS_URL is missing; Arq pool is required for the relay."
            )
        from app.trigger_client import trigger_postclipper_relay

        await trigger_postclipper_relay(arq_job_name, args)
        return
    if pool is not None:
        await pool.enqueue_job(arq_job_name, *args)
    else:
        background_tasks.add_task(coro, *args)
