"""
Arq worker: run with `cd backend && arq app.worker.WorkerSettings`
(requires REDIS_URL in backend/.env or environment).
"""
from __future__ import annotations

from arq.connections import RedisSettings

from app.bg_tasks import (
    run_generate_clips_pipeline,
    run_publish,
    run_regenerate_caption,
    run_render_drafts,
    run_suggest_alternative,
    run_suggest_clips,
    run_transcribe,
    run_twitch_ingest,
    run_upload_ingest,
    run_youtube_ingest,
)
from app.config import settings


async def task_youtube_ingest(ctx: dict, job_id: str, url: str) -> None:
    await run_youtube_ingest(job_id, url)


async def task_twitch_ingest(ctx: dict, job_id: str, url: str) -> None:
    await run_twitch_ingest(job_id, url)


async def task_upload_ingest(ctx: dict, job_id: str, saved_path: str) -> None:
    await run_upload_ingest(job_id, saved_path)


async def task_transcribe(ctx: dict, job_id: str) -> None:
    await run_transcribe(job_id)


async def task_suggest_clips(ctx: dict, job_id: str) -> None:
    await run_suggest_clips(job_id)


async def task_render_drafts(ctx: dict, job_id: str) -> None:
    await run_render_drafts(job_id)


async def task_generate_clips_pipeline(ctx: dict, job_id: str) -> None:
    await run_generate_clips_pipeline(job_id)


async def task_suggest_alternative(ctx: dict, candidate_id: str) -> None:
    await run_suggest_alternative(candidate_id)


async def task_publish(
    ctx: dict,
    candidate_id: str,
    platform: str,
    title: str | None,
    description: str | None,
) -> None:
    await run_publish(candidate_id, platform, title, description)


async def task_regenerate_caption(ctx: dict, candidate_id: str) -> None:
    await run_regenerate_caption(candidate_id)


class WorkerSettings:
    functions = [
        task_youtube_ingest,
        task_twitch_ingest,
        task_upload_ingest,
        task_transcribe,
        task_suggest_clips,
        task_render_drafts,
        task_generate_clips_pipeline,
        task_suggest_alternative,
        task_publish,
        task_regenerate_caption,
    ]
    # Same REDIS_URL as the API; falls back to local Redis for dev (e.g. docker compose).
    redis_settings = RedisSettings.from_dsn(settings.redis_url or "redis://127.0.0.1:6379/0")
    # Allow long FFmpeg / yt-dlp jobs
    job_timeout = 86400
    max_tries = 2
