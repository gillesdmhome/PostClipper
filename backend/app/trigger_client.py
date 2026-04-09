"""Trigger.dev REST trigger — offloads enqueue to Trigger workers that call back to /internal/trigger-dev/relay."""
from __future__ import annotations

from typing import Any

import httpx

from urllib.parse import quote

from app.config import settings


async def trigger_postclipper_relay(job_name: str, args: tuple[Any, ...]) -> None:
    """POST to Trigger.dev API; run returns quickly so the API event loop stays free."""
    key = settings.trigger_secret_key
    if not key:
        raise RuntimeError("trigger_postclipper_relay called without TRIGGER_SECRET_KEY")
    base = settings.trigger_api_base.rstrip("/")
    task_id = quote(settings.trigger_relay_task_id, safe="-_.~")
    url = f"{base}/api/v1/tasks/{task_id}/trigger"
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={"payload": {"jobName": job_name, "args": list(args)}},
        )
        r.raise_for_status()
