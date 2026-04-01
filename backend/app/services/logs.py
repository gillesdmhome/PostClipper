from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobLog


async def add_log(session: AsyncSession, job_id: str, message: str, level: str = "info") -> None:
    session.add(JobLog(job_id=job_id, message=message, level=level))


async def list_logs(session: AsyncSession, job_id: str, limit: int = 200):
    q = (
        select(JobLog)
        .where(JobLog.job_id == job_id)
        .order_by(JobLog.created_at.desc())
        .limit(limit)
    )
    r = await session.execute(q)
    return list(reversed(r.scalars().all()))
