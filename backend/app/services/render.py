from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from app.services.captions import build_clip_caption_lines, segment_fallback_lines
from app.services.ffmpeg_util import ffmpeg_binary, run_cmd
from app.services.ingest import ensure_dirs


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _caption_lines_for_clip(
    segments: list[dict], start_sec: float, end_sec: float
) -> List[Tuple[float, float, str]]:
    """
    Prefer word-synced, chunked lines (speech-relevant). Fallback to one line per segment.
    """
    lines = build_clip_caption_lines(segments, start_sec, end_sec)
    if not lines:
        lines = segment_fallback_lines(segments, start_sec, end_sec)
    return lines


def segments_to_ass_for_range(
    segments: list[dict], start_sec: float, end_sec: float, video_width: int = 1080
) -> str:
    """Build ASS subtitles timed to clip audio: word-level when available, else segment blocks."""
    lines = []
    lines.append("[Script Info]")
    lines.append("Title: clip-social")
    lines.append("ScriptType: v4.00+")
    lines.append("")
    lines.append("[V4+ Styles]")
    lines.append(
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
    )
    # Subtitle style: smaller text, bottom-center, comfortable bottom margin.
    # For 1080px wide video, aim for ~28-34px font.
    font_size = max(28, video_width // 34)
    margin_v = int(video_width * 0.09)
    lines.append(
        f"Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,"
        f"0,0,0,0,100,100,0,0,1,2,1,2,0,0,{margin_v},1"
    )
    lines.append("")
    lines.append("[Events]")
    lines.append("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text")

    def fmt_ass_time(t: float) -> str:
        t = max(0, t)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        cs = int(round((s - int(s)) * 100))
        sec_i = int(s)
        return f"{h}:{m:02d}:{sec_i:02d}.{cs:02d}"

    for rel_start, rel_end, raw_text in _caption_lines_for_clip(segments, start_sec, end_sec):
        text = _escape_ass(str(raw_text).strip())
        if not text:
            continue
        lines.append(
            f"Dialogue: 0,{fmt_ass_time(rel_start)},{fmt_ass_time(rel_end)},Default,,0,0,0,,{text}"
        )

    return "\n".join(lines)


def render_vertical_clip(
    job_id: str,
    mezzanine_path: str,
    start_sec: float,
    end_sec: float,
    segments: list[dict],
    out_name: str,
    *,
    height: int = 1920,
    width: int = 1080,
) -> Tuple[bool, str, Optional[str]]:
    """
    Crop/pad mezzanine to 9:16, burn captions, trim to [start,end].
    Assumes mezzanine is landscape or standard; uses center crop.
    """
    dirs = ensure_dirs(job_id)
    out = dirs["drafts"] / out_name
    out.parent.mkdir(parents=True, exist_ok=True)

    ass_content = segments_to_ass_for_range(segments, start_sec, end_sec, video_width=width)
    ass_file = out.with_suffix(".ass")
    ass_file.write_text(ass_content, encoding="utf-8")
    ass_name = ass_file.name

    duration = max(0.5, end_sec - start_sec)
    try:
        ffmpeg = ffmpeg_binary()
    except FileNotFoundError as e:
        return False, str(e), None
    # Run ffmpeg with cwd=out.parent so subtitles= uses a simple relative path (Windows-safe).
    vf = (
        f"scale=-2:{height},crop={width}:{height}:(iw-{width})/2:(ih-{height})/2,"
        f"subtitles={ass_name}"
    )

    args = [
        ffmpeg,
        "-y",
        "-ss",
        str(start_sec),
        "-t",
        str(duration),
        "-i",
        mezzanine_path,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(out.name),
    ]
    code, _, err = run_cmd(args, timeout=1800, cwd=str(out.parent))

    if code != 0:
        return False, err[-4000:] if err else "ffmpeg render failed", None
    return True, "", str(out.resolve())
