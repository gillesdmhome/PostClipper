from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional, Tuple

from app.services.ingest import ensure_dirs

_log = logging.getLogger(__name__)


def _whisper_device_compute() -> Tuple[str, str]:
    """Use CUDA when available (faster); else CPU int8."""
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda", "float16"
    except ImportError:
        pass
    return "cpu", "int8"


def _placeholder_segments(duration: Optional[float]) -> list[dict[str, Any]]:
    """When Whisper is unavailable, generate coarse segments for pipeline testing."""
    if not duration or duration <= 0:
        duration = 120.0
    chunk = 12.0
    segments = []
    t = 0.0
    idx = 0
    while t < min(duration, 600):
        end = min(t + chunk, duration)
        segments.append(
            {
                "start": t,
                "end": end,
                "text": f"Placeholder segment {idx + 1}. Install faster-whisper for real transcription.",
            }
        )
        t = end
        idx += 1
        if len(segments) >= 40:
            break
    return segments


def transcript_raw_needs_retranscribe(raw_json_path: Optional[str]) -> bool:
    """
    True when there is no usable ASR JSON on disk, or it was written by the
    placeholder path (so "generate clips" should run Whisper again).
    """
    if not raw_json_path:
        return True
    p = Path(raw_json_path)
    if not p.is_file():
        return True
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return True
    if data.get("engine") == "placeholder":
        return True
    segs = data.get("segments") or []
    if segs and "Install faster-whisper" in (segs[0].get("text") or ""):
        return True
    return False


def transcribe_mezzanine(
    job_id: str, mezzanine_path: str, duration_seconds: Optional[float]
) -> tuple[bool, str, dict]:
    dirs = ensure_dirs(job_id)
    raw_path = dirs["transcripts"] / "whisper_raw.json"
    segments: list[dict[str, Any]]

    try:
        from faster_whisper import WhisperModel  # type: ignore

        device, compute_type = _whisper_device_compute()
        _log.info("faster-whisper: model=base device=%s compute_type=%s", device, compute_type)
        try:
            model = WhisperModel("base", device=device, compute_type=compute_type)
        except Exception as e:
            if device == "cuda":
                _log.warning("Whisper CUDA init failed (%s); using CPU", e)
                model = WhisperModel("base", device="cpu", compute_type="int8")
            else:
                raise
        segs_out = []
        segments_iter, _info = model.transcribe(
            mezzanine_path,
            beam_size=5,
            vad_filter=True,
            word_timestamps=True,
        )
        for seg in segments_iter:
            entry: dict[str, Any] = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            }
            if getattr(seg, "words", None):
                entry["words"] = [
                    {"word": w.word.strip(), "start": float(w.start), "end": float(w.end)}
                    for w in seg.words
                ]
            segs_out.append(entry)
        segments = segs_out
        payload = {"engine": "faster-whisper", "segments": segments}
    except ImportError:
        segments = _placeholder_segments(duration_seconds)
        payload = {"engine": "placeholder", "segments": segments}
    except Exception as e:
        return False, str(e), {}

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    full_text = " ".join(s["text"] for s in segments)
    return True, "", {
        "raw_json_path": str(raw_path.resolve()),
        "language": None,
        "segments": segments,
        "full_text": full_text,
    }
