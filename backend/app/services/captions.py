"""
Build timed caption lines for a clip window so text matches spoken content.

Uses word-level timings from ASR when present; otherwise interpolates words
within each segment for alignment; falls back to one line per segment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List, Optional, Tuple

# Short-form style: a few words at a time, readable on mobile
DEFAULT_MAX_WORDS = 4
DEFAULT_MAX_CHARS = 40


def merge_segments_from_storage(
    raw_json_path: Optional[str], fallback_segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """
    Prefer ASR JSON on disk (includes word timestamps when Whisper produced them).
    Otherwise use DB-backed segment dicts.
    """
    if raw_json_path:
        p = Path(raw_json_path)
        if p.is_file():
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                segs = data.get("segments")
                if isinstance(segs, list) and segs:
                    return segs
            except (OSError, json.JSONDecodeError):
                pass
    return fallback_segments


def _synthetic_words_from_segment(
    seg: dict[str, Any], clip_start: float, clip_end: float
) -> List[Tuple[float, float, str]]:
    """Split segment text into words with linear time interpolation (no word timestamps)."""
    s0, s1 = float(seg["start"]), float(seg["end"])
    overlap_start = max(s0, clip_start)
    overlap_end = min(s1, clip_end)
    dur = overlap_end - overlap_start
    if dur <= 0:
        return []
    parts = str(seg.get("text", "")).split()
    if not parts:
        return []
    n = len(parts)
    step = dur / n
    out = []
    for i, p in enumerate(parts):
        ws = overlap_start + i * step
        we = overlap_start + (i + 1) * step
        out.append((ws, we, p))
    return out


def _collect_words_for_clip(
    segments: list[dict[str, Any]], clip_start: float, clip_end: float
) -> List[Tuple[float, float, str]]:
    """All word-level events overlapping [clip_start, clip_end], absolute times."""
    events: List[Tuple[float, float, str]] = []
    for seg in segments:
        s0, s1 = float(seg["start"]), float(seg["end"])
        if s1 <= clip_start or s0 >= clip_end:
            continue

        words = seg.get("words")
        if words and isinstance(words, list):
            for w in words:
                if not isinstance(w, dict):
                    continue
                wt = str(w.get("word", w.get("text", ""))).strip()
                if not wt:
                    continue
                ws = float(w["start"])
                we = float(w["end"])
                if we <= clip_start or ws >= clip_end:
                    continue
                events.append((max(ws, clip_start), min(we, clip_end), wt))
        else:
            events.extend(_synthetic_words_from_segment(seg, clip_start, clip_end))

    events.sort(key=lambda x: x[0])
    return events


def _chunk_words(
    word_events: List[Tuple[float, float, str]],
    clip_start: float,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> List[Tuple[float, float, str]]:
    """Group words into short on-screen lines (time = first→last word in chunk)."""
    if not word_events:
        return []

    rel: List[Tuple[float, float, str]] = []
    i = 0
    while i < len(word_events):
        chunk_words: List[Tuple[float, float, str]] = []
        j = i
        while j < len(word_events):
            cand = word_events[j]
            trial = chunk_words + [cand]
            line = " ".join(t[2] for t in trial)
            if len(trial) > max_words or len(line) > max_chars:
                break
            chunk_words = trial
            j += 1
            if len(chunk_words) >= max_words:
                break
        if not chunk_words:
            chunk_words = [word_events[i]]
            j = i + 1
        t0 = chunk_words[0][0] - clip_start
        t1 = chunk_words[-1][1] - clip_start
        text = " ".join(t[2] for t in chunk_words)
        rel.append((max(0.0, t0), max(0.0, t1), text))
        i = j

    return rel


def build_clip_caption_lines(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    *,
    max_words: int = DEFAULT_MAX_WORDS,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> List[Tuple[float, float, str]]:
    """
    Returns (relative_start, relative_end, text) for each caption line inside the clip.
    Text is only from speech overlapping the clip (relevant content).
    """
    words = _collect_words_for_clip(segments, clip_start, clip_end)
    if not words:
        return []

    chunked = _chunk_words(words, clip_start, max_words=max_words, max_chars=max_chars)
    clip_dur = max(0.01, clip_end - clip_start)
    # Clamp to clip duration
    out: List[Tuple[float, float, str]] = []
    for t0, t1, text in chunked:
        t0c = min(max(0.0, t0), clip_dur)
        t1c = min(max(t0c + 0.05, t1), clip_dur)
        out.append((t0c, t1c, text.strip()))
    return out


def fallback_context_line_from_transcript(
    segments: list[dict[str, Any]],
    clip_start: float,
    clip_end: float,
    *,
    max_chars: int = 120,
) -> str:
    """
    One contextual line from speech overlapping the clip (not timed subtitles).
    Used when hook_text is empty so the letterbox bar still has copy.
    """
    parts: list[str] = []
    for seg in segments:
        s0, s1 = float(seg["start"]), float(seg["end"])
        if s1 <= clip_start or s0 >= clip_end:
            continue
        t = str(seg.get("text", "")).strip()
        if t:
            parts.append(t)
    blob = " ".join(parts).strip()
    if not blob:
        return ""
    if len(blob) <= max_chars:
        return blob
    return blob[: max_chars - 1].rstrip() + "…"


def segment_fallback_lines(
    segments: list[dict[str, Any]], clip_start: float, clip_end: float
) -> List[Tuple[float, float, str]]:
    """One ASS line per transcript segment overlapping the clip (legacy behavior)."""
    lines: List[Tuple[float, float, str]] = []
    clip_dur = max(0.01, clip_end - clip_start)
    for seg in segments:
        s0 = float(seg["start"])
        s1 = float(seg["end"])
        if s1 <= clip_start or s0 >= clip_end:
            continue
        rel_start = max(0, s0 - clip_start)
        rel_end = min(clip_dur, s1 - clip_start)
        if rel_end <= rel_start:
            continue
        text = str(seg.get("text", "")).strip()
        if text:
            lines.append((rel_start, rel_end, text))
    return lines
