from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple

# Keywords that often correlate with engaging hooks (heuristic)
_HOOK_WORDS = re.compile(
    r"\b(never|always|secret|truth|stop|wrong|best|worst|why|how|watch|insane|crazy|free|hack)\b",
    re.I,
)

_log = logging.getLogger(__name__)


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def overlaps_excluded(
    start_sec: float, end_sec: float, exclude_ranges: List[Tuple[float, float]], pad: float = 2.0
) -> bool:
    """True if [start_sec, end_sec] overlaps any excluded window (with padding)."""
    for a, b in exclude_ranges:
        if end_sec + pad > a and start_sec - pad < b:
            return True
    return False


def _merge_short_segments(segments: list[dict[str, Any]], max_gap: float = 1.5) -> list[dict[str, Any]]:
    if not segments:
        return []
    merged = []
    cur = {**segments[0]}
    for s in segments[1:]:
        if s["start"] - cur["end"] <= max_gap:
            cur["end"] = max(cur["end"], s["end"])
            cur["text"] = (cur["text"] + " " + s["text"]).strip()
        else:
            merged.append(cur)
            cur = {**s}
    merged.append(cur)
    return merged


def candidate_windows_from_segments(
    segments: list[dict[str, Any]],
    *,
    target_min: float = 15.0,
    target_max: float = 55.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Build merged transcript segments and sliding time windows in [target_min, target_max].
    Returns (merged_segments, windows) where each window is {start, end, text}.
    """
    if not segments:
        return [], []
    merged = _merge_short_segments(segments)
    windows: list[dict[str, Any]] = []
    i = 0
    while i < len(merged):
        start = merged[i]["start"]
        j = i
        text_parts: list[str] = []
        end = start
        while j < len(merged):
            text_parts.append(merged[j]["text"])
            end = merged[j]["end"]
            dur = end - start
            text = " ".join(text_parts)
            if dur >= target_min:
                if dur <= target_max:
                    windows.append({"start": start, "end": end, "text": text})
                elif dur > target_max + 10:
                    break
            j += 1
        i += 1
    return merged, windows


def _hook_title_hashtags(text: str, *, target_min: float, dur: float) -> tuple[str, str, str]:
    prefix = text[: min(120, len(text))]
    title_words = text.split()[:8]
    suggested_title = " ".join(title_words).strip()[:80] or "Clip"
    return prefix[:200], suggested_title, "#shorts #clip"


def finalize_scored_candidates(
    scored: list[dict[str, Any]],
    *,
    merged: list[dict[str, Any]],
    target_min: float,
    target_max: float,
    max_candidates: int,
    exclude_ranges: Optional[List[Tuple[float, float]]] = None,
) -> list[dict[str, Any]]:
    """Sort by score, apply exclusion, cap count, single-window fallback."""
    scored = sorted(scored, key=lambda x: x["score"], reverse=True)
    ex = exclude_ranges or []
    if ex:
        scored = [x for x in scored if not overlaps_excluded(x["start_sec"], x["end_sec"], ex)]
    out = scored[:max_candidates]
    if not out and merged:
        start = float(merged[0]["start"])
        end = float(merged[-1]["end"])
        dur = max(target_min, min(target_max, end - start))
        hook, title, tags = _hook_title_hashtags(merged[0]["text"], target_min=target_min, dur=dur)
        out = [
            {
                "start_sec": start,
                "end_sec": min(end, start + dur),
                "score": 1.0,
                "hook_text": hook,
                "suggested_title": title,
                "suggested_hashtags": tags,
            }
        ]
        if ex and out:
            out = [x for x in out if not overlaps_excluded(x["start_sec"], x["end_sec"], ex)]
            if not out:
                return []
    return out


def suggest_clips_from_segments(
    segments: list[dict[str, Any]],
    *,
    target_min: float = 15.0,
    target_max: float = 55.0,
    max_candidates: int = 12,
    exclude_ranges: Optional[List[Tuple[float, float]]] = None,
) -> list[dict[str, Any]]:
    """
    Heuristic clip suggestion: merge adjacent transcript segments into windows
    in [target_min, target_max], score by hook words + word density.
    """
    if not segments:
        return []

    merged, candidates = candidate_windows_from_segments(
        segments, target_min=target_min, target_max=target_max
    )

    scored = []
    for c in candidates:
        text = c["text"]
        dur = max(0.1, c["end"] - c["start"])
        w = _word_count(text)
        density = w / dur
        hook = len(_HOOK_WORDS.findall(text))
        prefix = text[: min(120, len(text))]
        hook_boost = 0.5 * len(_HOOK_WORDS.findall(prefix))
        score = density * 2.0 + hook * 3.0 + hook_boost * 2.0 - abs(min(0, target_min - dur)) * 0.1
        hook_text, suggested_title, suggested_hashtags = _hook_title_hashtags(
            text, target_min=target_min, dur=dur
        )
        scored.append(
            {
                "start_sec": c["start"],
                "end_sec": c["end"],
                "score": round(score, 4),
                "hook_text": hook_text,
                "suggested_title": suggested_title,
                "suggested_hashtags": suggested_hashtags,
            }
        )

    return finalize_scored_candidates(
        scored,
        merged=merged,
        target_min=target_min,
        target_max=target_max,
        max_candidates=max_candidates,
        exclude_ranges=exclude_ranges,
    )


def suggest_clips(
    segments: list[dict[str, Any]],
    *,
    target_min: float = 15.0,
    target_max: float = 55.0,
    max_candidates: int = 12,
    exclude_ranges: Optional[List[Tuple[float, float]]] = None,
) -> list[dict[str, Any]]:
    """
    Dispatch to heuristic or embedding-based suggestion (see settings.suggest_engine).
    Falls back to heuristic if sentence-transformers is not installed or embedding run fails.
    """
    from app.config import settings

    engine = (settings.suggest_engine or "heuristic").strip().lower()
    if engine == "embeddings":
        try:
            from app.services import suggest_embeddings

            return suggest_embeddings.suggest_clips_embeddings(
                segments,
                target_min=target_min,
                target_max=target_max,
                max_candidates=max_candidates,
                exclude_ranges=exclude_ranges,
            )
        except ImportError as e:
            _log.warning("SUGGEST_ENGINE=embeddings but ML deps missing (%s); using heuristic", e)
        except Exception as e:
            _log.exception("Embedding suggest failed; using heuristic: %s", e)

    return suggest_clips_from_segments(
        segments,
        target_min=target_min,
        target_max=target_max,
        max_candidates=max_candidates,
        exclude_ranges=exclude_ranges,
    )
