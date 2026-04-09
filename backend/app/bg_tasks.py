"""Background async tasks (own DB session per task)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from sqlalchemy import delete, desc, nulls_last, select, update
from sqlalchemy.orm import selectinload

from app.database import async_session_maker
from app.models import (
    ClipCandidate,
    Job,
    JobStatus,
    PublishJob,
    PublishStatus,
    Transcript,
    TranscriptSegment,
)
from app.services.asr import transcribe_mezzanine, transcript_raw_needs_retranscribe
from app.services.ingest import download_with_ytdlp, ensure_dirs, ingest_pipeline
from app.services.logs import add_log
from app.services.publish import create_export_bundle, try_youtube_shorts_upload
from app.services.captions import merge_segments_from_storage
from app.services.render import render_vertical_clip
from app.services.suggest import suggest_clips
from app.services.scene_detect import detect_scene_cuts_ffmpeg
from app.services.boundaries import (
    boundaries_from_transcript,
    merge_boundaries,
    write_boundaries_json,
)
from app.services.captioning import generate_caption
from app.services.platforms import PRESETS, default_platforms
from app.services.fill_candidates import fill_non_overlapping

# Serialize suggest/render (and full clip pipeline) per job so concurrent runs do not delete
# clip_candidates while another session still holds ORM rows (StaleDataError on flush).
_job_clip_locks: dict[str, asyncio.Lock] = {}
_job_clip_locks_guard = asyncio.Lock()


async def _clip_pipeline_lock(job_id: str) -> asyncio.Lock:
    async with _job_clip_locks_guard:
        if job_id not in _job_clip_locks:
            _job_clip_locks[job_id] = asyncio.Lock()
        return _job_clip_locks[job_id]


async def _set_job_failed(session, job_id: str, msg: str):
    job = await session.get(Job, job_id)
    if job:
        job.status = JobStatus.failed.value
        job.error_message = msg[:2000]
        await add_log(session, job_id, msg, "error")


async def run_youtube_ingest(job_id: str, url: str):
    try:
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job:
                return
            job.status = JobStatus.ingesting.value
            job.error_message = None
            await add_log(session, job_id, f"YouTube ingest started: {url}")
            await session.commit()

        dirs = ensure_dirs(job_id)
        # yt-dlp / FFmpeg are synchronous; never run them on the asyncio loop — that stalls every
        # concurrent request on this process (e.g. GET /api/jobs/{id}) when REDIS_URL is unset and
        # FastAPI BackgroundTasks runs this coroutine on the API worker.
        ok, path, err = await asyncio.to_thread(download_with_ytdlp, url, dirs["raw"], "source")
        if not ok or not path:
            async with async_session_maker() as session:
                await _set_job_failed(session, job_id, err or "download failed")
                await session.commit()
            return

        ok2, err2, meta = await asyncio.to_thread(ingest_pipeline, job_id, path)
        async with async_session_maker() as session:
            if not ok2:
                await _set_job_failed(session, job_id, err2)
                await session.commit()
                return
            job = await session.get(Job, job_id)
            if job:
                job.mezzanine_path = meta["mezzanine_path"]
                job.proxy_path = meta["proxy_path"]
                job.duration_seconds = meta.get("duration_seconds")
                job.status = JobStatus.ingested.value
                await add_log(session, job_id, "Ingest complete; mezzanine ready")
            await session.commit()
    except Exception as e:
        async with async_session_maker() as s2:
            await _set_job_failed(s2, job_id, str(e))
            await s2.commit()


async def run_twitch_ingest(job_id: str, url: str):
    try:
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job:
                return
            job.status = JobStatus.ingesting.value
            job.error_message = None
            await add_log(session, job_id, f"Twitch ingest started: {url}")
            await session.commit()

        dirs = ensure_dirs(job_id)
        ok, path, err = await asyncio.to_thread(download_with_ytdlp, url, dirs["raw"], "source")
        if not ok or not path:
            async with async_session_maker() as session:
                await _set_job_failed(session, job_id, err or "download failed")
                await session.commit()
            return

        ok2, err2, meta = await asyncio.to_thread(ingest_pipeline, job_id, path)
        async with async_session_maker() as session:
            if not ok2:
                await _set_job_failed(session, job_id, err2)
                await session.commit()
                return
            job = await session.get(Job, job_id)
            if job:
                job.mezzanine_path = meta["mezzanine_path"]
                job.proxy_path = meta["proxy_path"]
                job.duration_seconds = meta.get("duration_seconds")
                job.status = JobStatus.ingested.value
                await add_log(session, job_id, "Ingest complete; mezzanine ready")
            await session.commit()
    except Exception as e:
        async with async_session_maker() as s2:
            await _set_job_failed(s2, job_id, str(e))
            await s2.commit()


async def run_upload_ingest(job_id: str, saved_path: str):
    try:
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job:
                return
            job.status = JobStatus.ingesting.value
            job.error_message = None
            await add_log(session, job_id, f"Upload ingest: {saved_path}")
            await session.commit()

        ok2, err2, meta = await asyncio.to_thread(ingest_pipeline, job_id, Path(saved_path))
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job:
                return
            if not ok2:
                await _set_job_failed(session, job_id, err2)
                await session.commit()
                return
            job.mezzanine_path = meta["mezzanine_path"]
            job.proxy_path = meta["proxy_path"]
            job.duration_seconds = meta.get("duration_seconds")
            job.status = JobStatus.ingested.value
            await add_log(session, job_id, "Ingest complete; mezzanine ready")
            await session.commit()
    except Exception as e:
        async with async_session_maker() as s2:
            await _set_job_failed(s2, job_id, str(e))
            await s2.commit()


async def run_transcribe(job_id: str):
    async with async_session_maker() as session:
        try:
            job = await session.get(Job, job_id)
            if not job or not job.mezzanine_path:
                return
            job.status = JobStatus.transcribing.value
            await add_log(session, job_id, "Transcription started")
            await session.commit()

            ok, err, data = transcribe_mezzanine(job_id, job.mezzanine_path, job.duration_seconds)
            job = await session.get(Job, job_id)
            if not ok:
                await _set_job_failed(session, job_id, err)
                await session.commit()
                return

            tr_old = await session.execute(select(Transcript).where(Transcript.job_id == job_id))
            old = tr_old.scalar_one_or_none()
            if old:
                await session.delete(old)
                await session.flush()

            tr = Transcript(
                job_id=job_id,
                raw_json_path=data["raw_json_path"],
                full_text=data.get("full_text"),
                language=data.get("language"),
            )
            session.add(tr)
            await session.flush()
            for seg in data.get("segments", []):
                session.add(
                    TranscriptSegment(
                        transcript_id=tr.id,
                        start_sec=float(seg["start"]),
                        end_sec=float(seg["end"]),
                        text=str(seg["text"]),
                    )
                )
            job.status = JobStatus.transcribed.value
            await add_log(session, job_id, "Transcription complete")
            await session.commit()
        except Exception as e:
            await session.rollback()
            async with async_session_maker() as s2:
                await _set_job_failed(s2, job_id, str(e))
                await s2.commit()


async def _run_suggest_clips_impl(job_id: str):
    async with async_session_maker() as session:
        try:
            job = await session.get(Job, job_id)
            if not job:
                return
            q = await session.execute(
                select(Transcript).options(selectinload(Transcript.segments)).where(Transcript.job_id == job_id)
            )
            tr = q.scalar_one_or_none()
            if not tr or not tr.segments:
                await _set_job_failed(session, job_id, "No transcript segments; run transcribe first")
                await session.commit()
                return

            job.status = JobStatus.suggesting.value
            await add_log(session, job_id, "Clip suggestion running")
            await session.commit()

            segs = [{"start": s.start_sec, "end": s.end_sec, "text": s.text} for s in tr.segments]

            # Boundary detection (scene cuts + transcript pauses/punctuation) to avoid mid-scene cuts.
            scene_cuts: list[float] = []
            if job.mezzanine_path:
                await add_log(session, job_id, "Detecting scene cuts (ffmpeg) for better clip boundaries")
                await session.commit()
                sd = await asyncio.to_thread(
                    detect_scene_cuts_ffmpeg,
                    job_id,
                    job.mezzanine_path,
                    threshold=0.35,
                    min_gap_sec=0.7,
                    write_json=True,
                )
                scene_cuts = sd.cuts
                if sd.raw_stderr_tail:
                    await add_log(session, job_id, f"Scene detect: found {len(scene_cuts)} cuts")
                    await session.commit()

            tb = boundaries_from_transcript(segs, min_pause_sec=0.85)
            b = merge_boundaries(scene_cuts=scene_cuts, transcript_boundaries=tb)
            write_boundaries_json(job_id, b)

            # Platform-aware suggestion: generate multiple sets with platform-specific length caps.
            suggested: list[dict] = []
            for plat in default_platforms():
                preset = PRESETS[plat]
                exclude: list[tuple[float, float]] = []
                s_plat = suggest_clips(
                    segs,
                    target_min=preset.target_min,
                    target_max=min(preset.target_max, preset.hard_max),
                    max_candidates=preset.max_candidates,
                    exclude_ranges=exclude,
                    boundaries=b.merged,
                    boundary_scene_cuts=b.scene_cuts,
                    boundary_pauses=b.pauses,
                    boundary_punctuation_ends=b.punctuation_ends,
                )
                # If we got too few, fill using boundary-to-boundary windows (still non-overlapping).
                s_plat = fill_non_overlapping(
                    s_plat,
                    boundaries=b.merged,
                    duration_sec=job.duration_seconds,
                    target_min=preset.target_min,
                    target_max=preset.target_max,
                    hard_max=preset.hard_max,
                    want_total=preset.max_candidates,
                )
                for x in s_plat:
                    x["platform"] = plat
                suggested.extend(s_plat)

            await session.execute(delete(ClipCandidate).where(ClipCandidate.job_id == job_id))
            for s in suggested:
                start_sec = float(s["start_sec"])
                end_sec = float(s["end_sec"])
                excerpt = " ".join(
                    str(x.get("text", "")).strip()
                    for x in segs
                    if float(x.get("end", 0.0)) >= start_sec and float(x.get("start", 0.0)) <= end_sec
                ).strip()
                cap = await asyncio.to_thread(
                    generate_caption,
                    job_id=job_id,
                    platform=(s.get("platform") or "shortform"),
                    start_sec=start_sec,
                    end_sec=end_sec,
                    segments=segs,
                    transcript_excerpt=excerpt[:2000],
                    suggested_title=s.get("suggested_title"),
                    hook_text=s.get("hook_text"),
                    suggested_hashtags=s.get("suggested_hashtags"),
                    force_regen=False,
                )
                session.add(
                    ClipCandidate(
                        job_id=job_id,
                        start_sec=start_sec,
                        end_sec=end_sec,
                        score=s.get("score"),
                        platform=s.get("platform"),
                        hook_text=cap.hook or s.get("hook_text"),
                        suggested_title=cap.title or s.get("suggested_title"),
                        suggested_hashtags=cap.hashtags or s.get("suggested_hashtags"),
                        suggested_description=cap.description,
                        review_status="pending",
                    )
                )
            job.status = JobStatus.suggested.value
            await add_log(session, job_id, f"Suggested {len(suggested)} clip candidates")
            await session.commit()
        except Exception as e:
            await session.rollback()
            async with async_session_maker() as s2:
                await _set_job_failed(s2, job_id, str(e))
                await s2.commit()


async def run_suggest_clips(job_id: str):
    async with await _clip_pipeline_lock(job_id):
        await _run_suggest_clips_impl(job_id)


async def _run_render_drafts_impl(job_id: str):
    async with async_session_maker() as session:
        try:
            job = await session.get(Job, job_id)
            if not job or not job.mezzanine_path:
                return
            mezzanine_path = job.mezzanine_path

            q = await session.execute(
                select(Transcript).options(selectinload(Transcript.segments)).where(Transcript.job_id == job_id)
            )
            tr = q.scalar_one_or_none()
            if not tr or not tr.segments:
                await _set_job_failed(session, job_id, "No transcript; cannot render drafts")
                await session.commit()
                return

            cq = await session.execute(
                select(ClipCandidate)
                .where(ClipCandidate.job_id == job_id)
                .order_by(nulls_last(desc(ClipCandidate.score)))
            )
            candidates = list(cq.scalars().all())
            if not candidates:
                await _set_job_failed(session, job_id, "No candidates; run suggest-clips first")
                await session.commit()
                return

            # Detach ORM rows so a concurrent suggest pass cannot leave stale instances that flush
            # UPDATEs against deleted PKs (StaleDataError: 0 rows matched).
            plan = [
                (
                    c.id,
                    float(c.start_sec),
                    float(c.end_sec),
                    c.platform,
                    c.hook_text,
                    c.suggested_title,
                )
                for c in candidates
            ]
            for c in candidates:
                session.expunge(c)

            job.status = JobStatus.rendering.value
            await add_log(session, job_id, f"Rendering {len(plan)} drafts (letterbox context captions)")
            await session.commit()

            fallback_segs = [
                {"start": float(s.start_sec), "end": float(s.end_sec), "text": s.text}
                for s in tr.segments
            ]
            segments = merge_segments_from_storage(tr.raw_json_path, fallback_segs)
            for cid, start_sec, end_sec, platform, hook_text, suggested_title in plan:
                out_name = f"draft_{cid[:8]}.mp4"
                preset = PRESETS.get(platform or "", PRESETS["tiktok"])
                ok, err, path = render_vertical_clip(
                    job_id,
                    mezzanine_path,
                    start_sec,
                    end_sec,
                    segments,
                    out_name,
                    width=preset.width,
                    height=preset.height,
                    letterbox_bottom_px=preset.letterbox_bottom_px,
                    hook_text=hook_text,
                    suggested_title=suggested_title,
                )
                if not ok:
                    await add_log(session, job_id, f"Render failed for candidate {cid}: {err}", "error")
                    continue
                if path:
                    await session.execute(
                        update(ClipCandidate)
                        .where(ClipCandidate.id == cid)
                        .values(draft_video_path=path)
                    )
            job = await session.get(Job, job_id)
            if job:
                job.status = JobStatus.rendered.value
            await add_log(session, job_id, "Render pass complete")
            await session.commit()
        except Exception as e:
            await session.rollback()
            async with async_session_maker() as s2:
                await _set_job_failed(s2, job_id, str(e))
                await s2.commit()


async def run_render_drafts(job_id: str):
    async with await _clip_pipeline_lock(job_id):
        await _run_render_drafts_impl(job_id)


async def run_suggest_alternative(old_candidate_id: str) -> None:
    """Mark candidate rejected, add one new non-overlapping clip + render its draft."""
    job_id_for_err: str | None = None
    try:
        async with async_session_maker() as session:
            old = await session.get(ClipCandidate, old_candidate_id)
            if not old:
                return
            job_id_for_err = old.job_id
            job = await session.get(Job, old.job_id)
            if not job or not job.mezzanine_path:
                await add_log(session, old.job_id, "Suggest alternative: job not ready", "error")
                await session.commit()
                return

            old.review_status = "rejected"
            await add_log(
                session,
                old.job_id,
                f"Candidate {old_candidate_id[:8]}… rejected — searching for another clip window",
            )
            await session.flush()

            cq = await session.execute(select(ClipCandidate).where(ClipCandidate.job_id == old.job_id))
            all_c = list(cq.scalars().all())
            exclude = [(float(c.start_sec), float(c.end_sec)) for c in all_c]

            q_tr = await session.execute(
                select(Transcript)
                .options(selectinload(Transcript.segments))
                .where(Transcript.job_id == old.job_id)
            )
            tr = q_tr.scalar_one_or_none()
            if not tr or not tr.segments:
                await add_log(session, old.job_id, "No transcript; cannot suggest alternative", "error")
                await session.commit()
                return

            segs = [{"start": s.start_sec, "end": s.end_sec, "text": s.text} for s in tr.segments]
            suggested = suggest_clips(segs, exclude_ranges=exclude, max_candidates=32)
            if not suggested:
                await add_log(
                    session,
                    old.job_id,
                    "No alternative clip found (try a longer source or trim exclusions)",
                    "error",
                )
                await session.commit()
                return

            s0 = suggested[0]
            new_c = ClipCandidate(
                job_id=old.job_id,
                start_sec=s0["start_sec"],
                end_sec=s0["end_sec"],
                score=s0.get("score"),
                hook_text=s0.get("hook_text"),
                suggested_title=s0.get("suggested_title"),
                suggested_hashtags=s0.get("suggested_hashtags"),
                review_status="pending",
            )
            session.add(new_c)
            await session.flush()
            new_id = new_c.id
            jid = old.job_id
            mezz = job.mezzanine_path
            raw_path = tr.raw_json_path

            fallback_segs = [
                {"start": float(s.start_sec), "end": float(s.end_sec), "text": s.text}
                for s in tr.segments
            ]
            await session.commit()

        merged = merge_segments_from_storage(raw_path, fallback_segs)
        out_name = f"draft_{new_id[:8]}.mp4"
        ok, err, path = render_vertical_clip(
            jid,
            mezz,
            s0["start_sec"],
            s0["end_sec"],
            merged,
            out_name,
            hook_text=s0.get("hook_text"),
            suggested_title=s0.get("suggested_title"),
        )
        async with async_session_maker() as s_up:
            nc = await s_up.get(ClipCandidate, new_id)
            if nc:
                if ok and path:
                    nc.draft_video_path = path
                    await add_log(s_up, jid, f"Alternative clip rendered ({new_id[:8]}…) — review in pending")
                else:
                    await add_log(
                        s_up,
                        jid,
                        f"Alternative added but render failed: {err[:500] if err else 'unknown'}",
                        "error",
                    )
            await s_up.commit()
    except Exception as e:
        async with async_session_maker() as s2:
            if job_id_for_err:
                await add_log(s2, job_id_for_err, f"Suggest alternative failed: {e}", "error")
            await s2.commit()


async def run_regenerate_caption(candidate_id: str) -> None:
    """Regenerate caption fields (LLM/heuristic) and re-render the draft so the letterbox updates."""
    job_id_for_err: str | None = None
    try:
        async with async_session_maker() as session:
            c = await session.get(ClipCandidate, candidate_id)
            if not c:
                return
            job_id_for_err = c.job_id
            job = await session.get(Job, c.job_id)
            if not job or not job.mezzanine_path:
                await add_log(session, c.job_id, "Regenerate caption: job not ready", "error")
                await session.commit()
                return

            q_tr = await session.execute(
                select(Transcript)
                .options(selectinload(Transcript.segments))
                .where(Transcript.job_id == c.job_id)
            )
            tr = q_tr.scalar_one_or_none()
            if not tr or not tr.segments:
                await add_log(session, c.job_id, "Regenerate caption: missing transcript", "error")
                await session.commit()
                return

            segs = [{"start": s.start_sec, "end": s.end_sec, "text": s.text} for s in tr.segments]
            start_sec = float(c.start_sec)
            end_sec = float(c.end_sec)
            excerpt = " ".join(
                str(x.get("text", "")).strip()
                for x in segs
                if float(x.get("end", 0.0)) >= start_sec and float(x.get("start", 0.0)) <= end_sec
            ).strip()

            await add_log(session, c.job_id, f"Regenerating caption for candidate {candidate_id[:8]}…")
            await session.commit()

            cap = await asyncio.to_thread(
                generate_caption,
                job_id=c.job_id,
                platform=c.platform or "shortform",
                start_sec=start_sec,
                end_sec=end_sec,
                segments=segs,
                transcript_excerpt=excerpt[:2000],
                suggested_title=c.suggested_title,
                hook_text=c.hook_text,
                suggested_hashtags=c.suggested_hashtags,
                force_regen=True,
            )

            c.hook_text = cap.hook or c.hook_text
            c.suggested_title = cap.title or c.suggested_title
            c.suggested_hashtags = cap.hashtags or c.suggested_hashtags
            c.suggested_description = cap.description
            await session.flush()

            # Render immediately with updated letterbox text.
            preset = PRESETS.get(c.platform or "", PRESETS["tiktok"])
            fallback_segs = [
                {"start": float(s.start_sec), "end": float(s.end_sec), "text": s.text}
                for s in tr.segments
            ]
            merged = merge_segments_from_storage(tr.raw_json_path, fallback_segs)
            out_name = f"draft_{candidate_id[:8]}.mp4"
            await session.commit()

        ok, err, path = render_vertical_clip(
            job_id_for_err,
            job.mezzanine_path,
            start_sec,
            end_sec,
            merged,
            out_name,
            width=preset.width,
            height=preset.height,
            letterbox_bottom_px=preset.letterbox_bottom_px,
            hook_text=cap.hook,
            suggested_title=cap.title,
        )
        async with async_session_maker() as s_up:
            c2 = await s_up.get(ClipCandidate, candidate_id)
            if c2:
                if ok and path:
                    c2.draft_video_path = path
                    await add_log(s_up, c2.job_id, f"Caption regenerated and draft updated ({candidate_id[:8]}…)")
                else:
                    await add_log(s_up, c2.job_id, f"Caption regenerated but render failed: {err}", "error")
            await s_up.commit()
    except Exception as e:
        async with async_session_maker() as s2:
            if job_id_for_err:
                await add_log(s2, job_id_for_err, f"Regenerate caption failed: {e}", "error")
            await s2.commit()


async def run_generate_clips_pipeline(job_id: str) -> None:
    """
    Triggered when the user asks to generate clips: run transcribe if missing or still
    on placeholder ASR, then suggest candidates, then render drafts.
    """
    async with await _clip_pipeline_lock(job_id):
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job:
                return
            if not job.mezzanine_path:
                await _set_job_failed(session, job_id, "Mezzanine not ready")
                await session.commit()
                return
            ext = await session.execute(select(Transcript).where(Transcript.job_id == job_id))
            tr = ext.scalar_one_or_none()
            needs_transcribe = tr is None or transcript_raw_needs_retranscribe(tr.raw_json_path)
            await add_log(
                session,
                job_id,
                "Clip generation started: transcribe if needed → suggest clips → render drafts",
            )
            await session.commit()

        if needs_transcribe:
            await run_transcribe(job_id)
            async with async_session_maker() as session:
                job = await session.get(Job, job_id)
                if not job or job.status == JobStatus.failed.value:
                    return

        await _run_suggest_clips_impl(job_id)
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if not job or job.status == JobStatus.failed.value:
                return

        await _run_render_drafts_impl(job_id)
        async with async_session_maker() as session:
            job = await session.get(Job, job_id)
            if job and job.status != JobStatus.failed.value:
                await add_log(session, job_id, "Clip generation finished — drafts ready to review")
                await session.commit()


async def run_publish(candidate_id: str, platform: str, title: str | None, description: str | None):
    async with async_session_maker() as session:
        try:
            c = await session.get(ClipCandidate, candidate_id)
            if not c:
                return
            job = await session.get(Job, c.job_id)
            if not job:
                return

            video_path = c.draft_video_path or job.mezzanine_path
            if not video_path:
                pj = PublishJob(
                    job_id=c.job_id,
                    candidate_id=candidate_id,
                    platform=platform,
                    status=PublishStatus.failed.value,
                    error_message="No rendered draft; run render first",
                )
                session.add(pj)
                await session.commit()
                return

            pj = PublishJob(
                job_id=c.job_id,
                candidate_id=candidate_id,
                platform=platform,
                status=PublishStatus.queued.value,
            )
            session.add(pj)
            await session.flush()

            meta = {
                "platform": platform,
                "title": title or c.suggested_title,
                "description": description or (c.hook_text or ""),
                "hashtags": c.suggested_hashtags,
                "start_sec": c.start_sec,
                "end_sec": c.end_sec,
            }

            pj_id = pj.id
            if platform == "youtube_shorts":
                pj.status = PublishStatus.uploading.value
                await session.commit()
                ok, err, vid = try_youtube_shorts_upload(
                    video_path,
                    title or c.suggested_title or "Short",
                    (description or "") + "\n\n" + (c.suggested_hashtags or ""),
                )
                async with async_session_maker() as s_up:
                    pj2 = await s_up.get(PublishJob, pj_id)
                    if pj2:
                        if ok and vid:
                            pj2.status = PublishStatus.posted.value
                            pj2.external_id = vid
                        else:
                            pj2.status = PublishStatus.failed.value
                            pj2.error_message = err or "upload failed"
                    await s_up.commit()
                return

            # TikTok / Instagram: export bundle
            pj.status = PublishStatus.uploading.value
            await session.commit()
            ok, err, zpath = create_export_bundle(c.job_id, candidate_id, video_path, meta)
            async with async_session_maker() as s_up:
                pj2 = await s_up.get(PublishJob, pj_id)
                if pj2:
                    if ok and zpath:
                        pj2.status = PublishStatus.export_ready.value
                        pj2.export_bundle_path = zpath
                    else:
                        pj2.status = PublishStatus.failed.value
                        pj2.error_message = err or "export failed"
                await s_up.commit()
        except Exception as e:
            await session.rollback()
            async with async_session_maker() as s2:
                cand = await s2.get(ClipCandidate, candidate_id)
                if cand:
                    await add_log(s2, cand.job_id, f"Publish failed: {e}", "error")
                await s2.commit()
