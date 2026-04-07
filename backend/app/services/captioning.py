from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

from app.config import settings
from app.services.captions import fallback_context_line_from_transcript
from app.services.ingest import ensure_dirs


@dataclass(frozen=True)
class CaptionResult:
    title: str | None
    hook: str | None
    hashtags: str | None
    description: str | None
    engine: str


def _cache_path(job_id: str) -> Path:
    dirs = ensure_dirs(job_id)
    return dirs["transcripts"] / "captions_cache.json"


def _load_cache(job_id: str) -> dict[str, Any]:
    p = _cache_path(job_id)
    try:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}
    return {}


def _save_cache(job_id: str, cache: dict[str, Any]) -> None:
    p = _cache_path(job_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def _key(platform: str, start_sec: float, end_sec: float, transcript_text: str) -> str:
    h = hashlib.sha1()
    h.update(platform.encode("utf-8"))
    h.update(f"{start_sec:.3f}-{end_sec:.3f}".encode("utf-8"))
    h.update(transcript_text.strip().encode("utf-8", errors="ignore"))
    return h.hexdigest()


def _heuristic_caption(
    *,
    segments: list[dict],
    start_sec: float,
    end_sec: float,
    suggested_title: Optional[str],
    hook_text: Optional[str],
    suggested_hashtags: Optional[str],
) -> CaptionResult:
    title = (suggested_title or "").strip() or None
    hook = (hook_text or "").strip()
    if not hook:
        hook = fallback_context_line_from_transcript(segments, start_sec, end_sec).strip()
    hook = hook or None
    tags = (suggested_hashtags or "").strip() or None
    desc = hook
    return CaptionResult(title=title, hook=hook, hashtags=tags, description=desc, engine="heuristic")


def generate_caption(
    *,
    job_id: str,
    platform: str,
    start_sec: float,
    end_sec: float,
    segments: list[dict],
    transcript_excerpt: str,
    suggested_title: Optional[str],
    hook_text: Optional[str],
    suggested_hashtags: Optional[str],
    force_regen: bool = False,
) -> CaptionResult:
    """
    Generate context-relevant captioning for letterbox + metadata.

    - Prefers local LLM (Ollama) if reachable.
    - Falls back to transcript heuristics.
    - Disk-caches results per job to make repeated renders cheap.
    """
    excerpt = (transcript_excerpt or "").strip()
    cache = _load_cache(job_id)
    k = _key(platform, start_sec, end_sec, excerpt)
    if not force_regen and k in cache:
        c = cache[k] or {}
        return CaptionResult(
            title=c.get("title"),
            hook=c.get("hook"),
            hashtags=c.get("hashtags"),
            description=c.get("description"),
            engine=c.get("engine") or "cache",
        )

    # Heuristic base (also used when LLM fails)
    base = _heuristic_caption(
        segments=segments,
        start_sec=start_sec,
        end_sec=end_sec,
        suggested_title=suggested_title,
        hook_text=hook_text,
        suggested_hashtags=suggested_hashtags,
    )

    # Local LLM attempt (free/open-source)
    try:
        if excerpt:
            prompt = (
                "You write short-form video captions for social media.\n"
                f"Platform: {platform}\n"
                f"Clip seconds: {max(0.5, end_sec - start_sec):.1f}\n"
                "Given this transcript excerpt, produce JSON with keys:\n"
                '- title (max 80 chars)\n'
                '- hook (max 220 chars, 1-2 lines, no quotes)\n'
                '- hashtags (space-separated, include 2-6 tags)\n'
                '- description (1-2 short sentences)\n'
                "Transcript excerpt:\n"
                f"{excerpt}\n"
                "Return ONLY valid JSON."
            )
            with httpx.Client(timeout=settings.ollama_timeout_sec) as client:
                r = client.post(
                    f"{settings.ollama_base_url.rstrip('/')}/api/generate",
                    json={
                        "model": settings.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.4},
                    },
                )
                r.raise_for_status()
                data = r.json()
                raw = (data.get("response") or "").strip()
                parsed = json.loads(raw)
                out = CaptionResult(
                    title=(str(parsed.get("title", "")).strip() or None),
                    hook=(str(parsed.get("hook", "")).strip() or None),
                    hashtags=(str(parsed.get("hashtags", "")).strip() or None),
                    description=(str(parsed.get("description", "")).strip() or None),
                    engine="ollama",
                )
                cache[k] = {
                    "title": out.title,
                    "hook": out.hook,
                    "hashtags": out.hashtags,
                    "description": out.description,
                    "engine": out.engine,
                    "model": settings.ollama_model,
                }
                _save_cache(job_id, cache)
                return out
    except Exception:
        pass

    cache[k] = {
        "title": base.title,
        "hook": base.hook,
        "hashtags": base.hashtags,
        "description": base.description,
        "engine": base.engine,
    }
    _save_cache(job_id, cache)
    return base

