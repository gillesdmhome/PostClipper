from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.config import settings
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models import PublishJob

router = APIRouter(prefix="/api/publish-jobs", tags=["publish"])


def _safe_under_data(abs_path: Path) -> bool:
    try:
        abs_path.resolve().relative_to(settings.data_dir.resolve())
        return True
    except ValueError:
        return False


@router.get("/{publish_job_id}/download")
async def download_bundle(
    publish_job_id: str,
    session: AsyncSession = Depends(get_db),
):
    pj = await session.get(PublishJob, publish_job_id)
    if not pj or not pj.export_bundle_path:
        raise HTTPException(404, "Bundle not available")
    p = Path(pj.export_bundle_path)
    if not p.is_file() or not _safe_under_data(p):
        raise HTTPException(404, "File missing")
    return FileResponse(
        p,
        media_type="application/zip",
        filename=f"clip_export_{publish_job_id[:8]}.zip",
    )
