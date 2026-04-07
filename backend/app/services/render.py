from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from app.services.captions import fallback_context_line_from_transcript
from app.services.ffmpeg_util import ffmpeg_binary, run_cmd
from app.services.ingest import ensure_dirs

# Bottom black bar (px) at output height 1920 — captions live here, not over the picture.
LETTERBOX_BOTTOM_PX = 260
DEFAULT_OUTPUT_HEIGHT = 1920
DEFAULT_OUTPUT_WIDTH = 1080


def _escape_ass(text: str) -> str:
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
        .replace("\n", r"\N")
    )


def _truncate_caption(s: str, max_chars: int = 200) -> str:
    s = s.strip()
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 1].rstrip() + "…"


def _compose_letterbox_text(
    hook_text: Optional[str],
    suggested_title: Optional[str],
    segments: list[dict],
    clip_start: float,
    clip_end: float,
) -> tuple[Optional[str], Optional[str]]:
    """
    Title line (smaller, above) + main hook line for the letterbox bar.
    Main line prefers hook_text; else one overlapping transcript snippet (not word-timed).
    """
    title = (suggested_title or "").strip() or None
    hook = (hook_text or "").strip()
    if not hook:
        hook = fallback_context_line_from_transcript(segments, clip_start, clip_end).strip()
    if not hook:
        return None, None
    if title and title == hook:
        title = None
    title = _truncate_caption(title, 80) if title else None
    hook = _truncate_caption(hook, 220)
    return title, hook


def letterbox_context_ass(
    *,
    duration_sec: float,
    video_width: int,
    video_height: int,
    title: Optional[str],
    hook: str,
) -> str:
    """
    Single full-clip ASS event: cinematic captions in the bottom letterbox (not synced subtitles).
    Uses \\pos for placement in the black bar; PlayRes matches the encoded frame.
    """
    lines: list[str] = [
        "[Script Info]",
        "Title: clip-social-letterbox",
        "ScriptType: v4.00+",
        f"PlayResX: {video_width}",
        f"PlayResY: {video_height}",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, "
        "BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, "
        "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Default,Arial,{max(32, video_width // 28)},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,"
        "1,0,0,0,100,100,0,0,1,3,1,2,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    # Anchor in bottom letterbox (not over the video)
    bar_top_y = video_height - LETTERBOX_BOTTOM_PX
    cx = video_width // 2
    if title:
        cy = bar_top_y + 110
        fs_title = max(22, video_width // 48)
        fs_hook = max(30, video_width // 34)
        body = (
            f"{{\\an2\\pos({cx},{cy})\\fs{fs_title}\\c&H9CA3AF&}}{_escape_ass(title)}"
            f"{{\\N\\r\\fs{fs_hook}\\c&HFFFFFF&}}{_escape_ass(hook)}"
        )
    else:
        cy = bar_top_y + 95
        fs_hook = max(32, video_width // 32)
        body = f"{{\\an2\\pos({cx},{cy})\\fs{fs_hook}\\c&HFFFFFF&}}{_escape_ass(hook)}"

    def fmt_ass_time(t: float) -> str:
        t = max(0, t)
        h = int(t // 3600)
        m = int((t % 3600) // 60)
        s = t % 60
        cs = int(round((s - int(s)) * 100))
        sec_i = int(s)
        return f"{h}:{m:02d}:{sec_i:02d}.{cs:02d}"

    end_t = max(0.2, duration_sec)
    lines.append(f"Dialogue: 0,{fmt_ass_time(0)},{fmt_ass_time(end_t)},Default,,0,0,0,,{body}")
    return "\n".join(lines)


def render_vertical_clip(
    job_id: str,
    mezzanine_path: str,
    start_sec: float,
    end_sec: float,
    segments: list[dict],
    out_name: str,
    *,
    height: int = DEFAULT_OUTPUT_HEIGHT,
    width: int = DEFAULT_OUTPUT_WIDTH,
    hook_text: Optional[str] = None,
    suggested_title: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Letterboxed 9:16: video fills the frame above a bottom black bar; context captions
    (hook / title / short transcript fallback) are drawn in the bar — not word-synced subtitles.
    """
    dirs = ensure_dirs(job_id)
    out = dirs["drafts"] / out_name
    out.parent.mkdir(parents=True, exist_ok=True)

    duration = max(0.5, end_sec - start_sec)
    content_h = height - LETTERBOX_BOTTOM_PX

    title, hook = _compose_letterbox_text(hook_text, suggested_title, segments, start_sec, end_sec)

    try:
        ffmpeg = ffmpeg_binary()
    except FileNotFoundError as e:
        return False, str(e), None

    # Scale + center-crop to width x content_h, then pad black at bottom for letterbox.
    scale_crop = (
        f"scale=-2:{content_h},crop={width}:{content_h}:(iw-{width})/2:(ih-{content_h})/2"
    )
    pad = f"pad={width}:{height}:0:0:black"

    if hook:
        ass_content = letterbox_context_ass(
            duration_sec=duration,
            video_width=width,
            video_height=height,
            title=title,
            hook=hook,
        )
        ass_file = out.with_suffix(".ass")
        ass_file.write_text(ass_content, encoding="utf-8")
        ass_name = ass_file.name
        vf = f"{scale_crop},{pad},subtitles={ass_name}"
    else:
        vf = f"{scale_crop},{pad}"

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
