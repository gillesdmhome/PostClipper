from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.services.ffmpeg_util import ffmpeg_binary, run_cmd
from app.services.ingest import ensure_dirs


@dataclass(frozen=True)
class SceneDetectResult:
    cuts: list[float]
    raw_stderr_tail: str | None = None


_PTS_TIME_RE = re.compile(r"pts_time:(?P<t>\d+(?:\.\d+)?)")


def detect_scene_cuts_ffmpeg(
    job_id: str,
    mezzanine_path: str,
    *,
    threshold: float = 0.35,
    min_gap_sec: float = 0.7,
    max_cuts: int = 2000,
    timeout_sec: int = 1800,
    write_json: bool = True,
) -> SceneDetectResult:
    """
    Extract approximate scene cut timestamps using FFmpeg's scene change score.

    This is intentionally dependency-light (no OpenCV / PySceneDetect). It trades accuracy for
    simplicity and speed, and is good enough to snap clip boundaries away from mid-scene cuts.
    """
    try:
        ffmpeg = ffmpeg_binary()
    except FileNotFoundError as e:
        return SceneDetectResult(cuts=[], raw_stderr_tail=str(e))

    thr = max(0.01, min(0.99, float(threshold)))
    vf = f"select='gt(scene,{thr})',showinfo"
    args = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-i",
        mezzanine_path,
        "-vf",
        vf,
        "-an",
        "-f",
        "null",
        "-",
    ]
    code, _, err = run_cmd(args, timeout=timeout_sec, cwd=str(Path(mezzanine_path).parent))
    if code != 0:
        tail = (err or "")[-4000:] if err else "ffmpeg scene detect failed"
        return SceneDetectResult(cuts=[], raw_stderr_tail=tail)

    cuts: list[float] = []
    last: Optional[float] = None
    for m in _PTS_TIME_RE.finditer(err or ""):
        try:
            t = float(m.group("t"))
        except Exception:
            continue
        if last is not None and (t - last) < min_gap_sec:
            continue
        cuts.append(t)
        last = t
        if len(cuts) >= max_cuts:
            break

    if write_json:
        dirs = ensure_dirs(job_id)
        out_path = dirs["transcripts"] / "scenes.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"engine": "ffmpeg_scene", "threshold": thr, "cuts_sec": cuts}, indent=2),
            encoding="utf-8",
        )

    return SceneDetectResult(cuts=cuts, raw_stderr_tail=(err or "")[-2000:] if err else None)

