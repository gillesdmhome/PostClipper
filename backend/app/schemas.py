from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class YoutubeIngest(BaseModel):
    url: str = Field(..., min_length=8)


class TwitchIngest(BaseModel):
    url: str = Field(..., min_length=8)


class JobSummary(BaseModel):
    id: str
    source_type: str
    source_url: Optional[str]
    original_filename: Optional[str]
    status: str
    mezzanine_path: Optional[str] = None
    proxy_path: Optional[str] = None
    duration_seconds: Optional[float]
    error_message: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class PublishJobOut(BaseModel):
    id: str
    platform: str
    status: str
    external_id: Optional[str]
    export_bundle_path: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TranscriptSegmentOut(BaseModel):
    id: str
    start_sec: float
    end_sec: float
    text: str

    model_config = {"from_attributes": True}


class TranscriptOut(BaseModel):
    id: str
    language: Optional[str]
    full_text: Optional[str]
    segments: List[TranscriptSegmentOut] = []

    model_config = {"from_attributes": True}


class ClipCandidateOut(BaseModel):
    id: str
    start_sec: float
    end_sec: float
    score: Optional[float]
    hook_text: Optional[str]
    suggested_title: Optional[str]
    suggested_hashtags: Optional[str]
    draft_video_path: Optional[str]
    approved: int
    review_status: str = "pending"
    publish_jobs: List[PublishJobOut] = []

    model_config = {"from_attributes": True}


class JobLogOut(BaseModel):
    id: str
    level: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class JobDetail(BaseModel):
    job: JobSummary
    transcript: Optional[TranscriptOut]
    candidates: List[ClipCandidateOut]
    logs: List[JobLogOut]


class CandidatePatch(BaseModel):
    start_sec: Optional[float] = None
    end_sec: Optional[float] = None
    hook_text: Optional[str] = None
    suggested_title: Optional[str] = None
    suggested_hashtags: Optional[str] = None
    approved: Optional[int] = None
    review_status: Optional[Literal["pending", "accepted", "rejected"]] = None


class PublishRequest(BaseModel):
    platform: Literal["youtube_shorts", "tiktok", "instagram_reels"]
    title: Optional[str] = None
    description: Optional[str] = None
