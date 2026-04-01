from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class JobStatus(str, enum.Enum):
    pending = "pending"
    ingesting = "ingesting"
    ingested = "ingested"
    transcribing = "transcribing"
    transcribed = "transcribed"
    suggesting = "suggesting"
    suggested = "suggested"
    rendering = "rendering"
    rendered = "rendered"
    failed = "failed"


class PublishStatus(str, enum.Enum):
    idle = "idle"
    queued = "queued"
    uploading = "uploading"
    posted = "posted"
    export_ready = "export_ready"
    failed = "failed"


class SourceType(str, enum.Enum):
    youtube = "youtube"
    twitch = "twitch"
    upload = "upload"


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type: Mapped[str] = mapped_column(String(32))
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    original_filename: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.pending.value)
    mezzanine_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    proxy_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    transcript: Mapped[Optional["Transcript"]] = relationship(back_populates="job", uselist=False, cascade="all, delete-orphan")
    candidates: Mapped[List["ClipCandidate"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    publish_jobs: Mapped[List["PublishJob"]] = relationship(back_populates="job", cascade="all, delete-orphan")
    ingest_logs: Mapped[List["JobLog"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    language: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    raw_json_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    job: Mapped["Job"] = relationship(back_populates="transcript")
    segments: Mapped[List["TranscriptSegment"]] = relationship(back_populates="transcript", cascade="all, delete-orphan")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    transcript_id: Mapped[str] = mapped_column(String(36), ForeignKey("transcripts.id", ondelete="CASCADE"))
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)

    transcript: Mapped["Transcript"] = relationship(back_populates="segments")


class ClipCandidate(Base):
    __tablename__ = "clip_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"))
    start_sec: Mapped[float] = mapped_column(Float)
    end_sec: Mapped[float] = mapped_column(Float)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hook_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    suggested_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    suggested_hashtags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    caption_overlay_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_video_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    approved: Mapped[int] = mapped_column(Integer, default=0)  # 0 draft 1 approved for publish
    review_status: Mapped[str] = mapped_column(
        String(16), default="pending"
    )  # pending | accepted | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="candidates")
    publish_jobs: Mapped[List["PublishJob"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"))
    candidate_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("clip_candidates.id", ondelete="SET NULL"), nullable=True)
    platform: Mapped[str] = mapped_column(String(32))  # youtube_shorts, tiktok, instagram_reels
    status: Mapped[str] = mapped_column(String(32), default=PublishStatus.idle.value)
    external_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    export_bundle_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="publish_jobs")
    candidate: Mapped[Optional["ClipCandidate"]] = relationship(back_populates="publish_jobs")


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"))
    level: Mapped[str] = mapped_column(String(16), default="info")
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    job: Mapped["Job"] = relationship(back_populates="ingest_logs")
