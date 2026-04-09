from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from app.services.ingest import ensure_dirs


@dataclass(frozen=True)
class Boundaries:
    scene_cuts: list[float]
    pauses: list[float]
    punctuation_ends: list[float]
    merged: list[float]


def _dedupe_sorted(times: Iterable[float], *, tol: float = 0.12) -> list[float]:
    out: list[float] = []
    last: Optional[float] = None
    for t in sorted(float(x) for x in times if x is not None and math.isfinite(float(x))):
        if t < 0:
            continue
        if last is None or abs(t - last) > tol:
            out.append(t)
            last = t
    return out


def boundaries_from_transcript(
    segments: list[dict[str, Any]],
    *,
    min_pause_sec: float = 0.85,
    punctuation_chars: str = ".?!",
) -> Boundaries:
    pauses: list[float] = []
    punct: list[float] = []
    last_end: Optional[float] = None
    for s in segments or []:
        try:
            start = float(s.get("start", 0.0))
            end = float(s.get("end", 0.0))
        except Exception:
            continue
        text = str(s.get("text", "") or "").strip()
        if last_end is not None:
            gap = start - last_end
            if gap >= float(min_pause_sec):
                pauses.append(start)
        last_end = end
        if text and text[-1] in punctuation_chars and end > 0:
            punct.append(end)
    merged = _dedupe_sorted([0.0, *pauses, *punct])
    return Boundaries(scene_cuts=[], pauses=_dedupe_sorted(pauses), punctuation_ends=_dedupe_sorted(punct), merged=merged)


def merge_boundaries(
    *,
    scene_cuts: list[float] | None,
    transcript_boundaries: Boundaries,
) -> Boundaries:
    sc = _dedupe_sorted(scene_cuts or [])
    merged = _dedupe_sorted([*transcript_boundaries.merged, *sc])
    return Boundaries(
        scene_cuts=sc,
        pauses=transcript_boundaries.pauses,
        punctuation_ends=transcript_boundaries.punctuation_ends,
        merged=merged,
    )


def write_boundaries_json(job_id: str, b: Boundaries) -> str:
    dirs = ensure_dirs(job_id)
    p = dirs["transcripts"] / "boundaries.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "scene_cuts_sec": b.scene_cuts,
        "pauses_sec": b.pauses,
        "punctuation_ends_sec": b.punctuation_ends,
        "boundaries_sec": b.merged,
    }
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(Path(p).resolve())

