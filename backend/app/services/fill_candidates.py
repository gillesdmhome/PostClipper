from __future__ import annotations

from typing import Any

from app.services.suggest import overlaps_excluded


def _choose_boundaries(boundaries: list[float], *, duration_sec: float | None) -> list[float]:
    b = sorted({float(x) for x in (boundaries or []) if x is not None})
    if not b or b[0] != 0.0:
        b = [0.0, *b]
    if duration_sec is not None and duration_sec > 0:
        end = float(duration_sec)
        if not b or abs(b[-1] - end) > 0.25:
            b.append(end)
    return b


def fill_non_overlapping(
    existing: list[dict[str, Any]],
    *,
    boundaries: list[float],
    duration_sec: float | None,
    target_min: float,
    target_max: float,
    hard_max: float,
    want_total: int,
    pad: float = 1.5,
    min_clip_sec: float = 6.0,
) -> list[dict[str, Any]]:
    """
    If suggestion yields too few candidates (common on short sources / weak transcripts),
    add additional non-overlapping windows using boundary-to-boundary intervals.
    """
    out = list(existing)
    if want_total <= 0 or len(out) >= want_total:
        return out

    b = _choose_boundaries(boundaries, duration_sec=duration_sec)
    if len(b) < 2:
        return out

    # Build exclusion list from existing.
    exclude: list[tuple[float, float]] = [(float(c["start_sec"]), float(c["end_sec"])) for c in out]

    # Use a smaller minimum on very short sources (but never below min_clip_sec).
    eff_min = max(min_clip_sec, min(target_min, hard_max))
    eff_max = max(eff_min, min(target_max, hard_max))

    # Greedy scan across boundaries to add windows.
    i = 0
    while i < len(b) - 1 and len(out) < want_total:
        start = b[i]
        # Find a reasonable end boundary within [eff_min, eff_max]
        end = None
        for j in range(i + 1, len(b)):
            cand_end = b[j]
            dur = cand_end - start
            if dur < eff_min:
                continue
            if dur > eff_max:
                break
            end = cand_end
        if end is None:
            i += 1
            continue
        if overlaps_excluded(start, end, exclude, pad=pad):
            i += 1
            continue
        out.append(
            {
                "start_sec": round(float(start), 3),
                "end_sec": round(float(end), 3),
                "score": 0.01,  # filler
                "hook_text": None,
                "suggested_title": "Clip",
                "suggested_hashtags": "#shorts #clip",
            }
        )
        exclude.append((float(start), float(end)))
        i += 1

    return out

