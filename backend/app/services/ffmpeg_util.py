from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import settings

# backend/ — resolve relative FFMPEG_PATH entries in .env regardless of process cwd
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _abs_tool_path(p: Path) -> Path:
    p = p.expanduser()
    return p if p.is_absolute() else (_BACKEND_DIR / p).resolve()


def _ffmpeg_tool_help() -> str:
    return (
        "FFmpeg/ffprobe not found. Set FFMPEG_PATH and FFPROBE_PATH in backend/.env to the full paths "
        "of ffmpeg.exe and ffprobe.exe (same folder is fine), or install FFmpeg and restart the app "
        "from a terminal where `ffmpeg` works. On Windows, winget installs under "
        "%LOCALAPPDATA%\\Microsoft\\WinGet\\Packages\\…\\bin\\."
    )


def _iter_windows_ffmpeg_exes() -> list[Path]:
    """Typical install locations when PATH is not visible to the API process (e.g. Cursor)."""
    found: list[Path] = []
    local = os.environ.get("LOCALAPPDATA") or ""
    if local:
        link = Path(local) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
        if link.is_file():
            found.append(link)
        pkgs = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if pkgs.is_dir():
            for d in pkgs.iterdir():
                du = d.name.upper()
                if "FFMPEG" in du and "GYAN" in du:
                    for p in d.rglob("ffmpeg.exe"):
                        found.append(p)
                        break
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pffb = Path(pf) / "ffmpeg" / "bin" / "ffmpeg.exe"
    if pffb.is_file():
        found.append(pffb)
    # Scoop default layout
    profile = os.environ.get("USERPROFILE", "")
    if profile:
        scoop = Path(profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe"
        if scoop.is_file():
            found.append(scoop)
    # Chocolatey shim / portable
    choco_bin = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey")) / "bin" / "ffmpeg.exe"
    if choco_bin.is_file():
        found.append(choco_bin)
    # De-dupe by resolved path while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in found:
        key = str(p.resolve())
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _probe_name() -> str:
    return "ffprobe.exe" if sys.platform == "win32" else "ffprobe"


def resolve_ffmpeg_ffprobe() -> tuple[str | None, str | None]:
    ff: str | None = None
    fp: str | None = None

    cfg_ff = settings.ffmpeg_path
    cfg_fp = settings.ffprobe_path
    if cfg_ff is not None:
        ap = _abs_tool_path(cfg_ff)
        if ap.is_file():
            ff = str(ap)
    if cfg_fp is not None:
        ap = _abs_tool_path(cfg_fp)
        if ap.is_file():
            fp = str(ap)

    if ff is None:
        w = shutil.which("ffmpeg")
        if w:
            ff = w
    if fp is None:
        w = shutil.which("ffprobe")
        if w:
            fp = w

    if ff is None and sys.platform == "win32":
        for p in _iter_windows_ffmpeg_exes():
            ff = str(p.resolve())
            break

    if fp is None and ff is not None:
        sibling = Path(ff).parent / _probe_name()
        if sibling.is_file():
            fp = str(sibling.resolve())

    if fp is None and sys.platform == "win32":
        for p in _iter_windows_ffmpeg_exes():
            sib = p.parent / _probe_name()
            if sib.is_file():
                fp = str(sib.resolve())
                if ff is None:
                    ff = str(p.resolve())
                break

    return ff, fp


def ffmpeg_binary() -> str:
    ff, _ = resolve_ffmpeg_ffprobe()
    if not ff:
        raise FileNotFoundError(_ffmpeg_tool_help())
    return ff


def ffprobe_binary() -> str:
    _, fp = resolve_ffmpeg_ffprobe()
    if not fp:
        raise FileNotFoundError(_ffmpeg_tool_help())
    return fp


def run_cmd(
    args: list[str],
    timeout: int | None = 600,
    cwd: str | None = None,
) -> tuple[int, str, str]:
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except FileNotFoundError as e:
        exe = args[0] if args else "command"
        msg = (
            f"{exe} not found ({e}). {_ffmpeg_tool_help()}"
        )
        return 127, "", msg
    return p.returncode, p.stdout or "", p.stderr or ""


def ffprobe_duration_seconds(path: Path) -> float | None:
    try:
        probe = ffprobe_binary()
    except FileNotFoundError:
        return None
    code, out, err = run_cmd(
        [
            probe,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            str(path),
        ],
        timeout=120,
    )
    if code != 0:
        return None
    try:
        data = json.loads(out)
        return float(data["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def normalize_to_mezzanine(
    src: Path,
    dst: Path,
    *,
    height: int = 720,
) -> tuple[bool, str]:
    """H.264 + AAC mezzanine for downstream ASR and editing."""
    try:
        ffmpeg = ffmpeg_binary()
    except FileNotFoundError as e:
        return False, str(e)
    dst.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale=-2:{height}"
    args = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "22",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    code, _, err = run_cmd(args, timeout=3600)
    if code != 0:
        return False, err[-4000:] if err else "ffmpeg failed"
    return True, ""


def make_proxy(src: Path, dst: Path, *, width: int = 426) -> tuple[bool, str]:
    """Low-res fast-preview proxy."""
    try:
        ffmpeg = ffmpeg_binary()
    except FileNotFoundError as e:
        return False, str(e)
    dst.parent.mkdir(parents=True, exist_ok=True)
    args = [
        ffmpeg,
        "-y",
        "-i",
        str(src),
        "-vf",
        f"scale={width}:-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(dst),
    ]
    code, _, err = run_cmd(args, timeout=3600)
    if code != 0:
        return False, err[-4000:] if err else "ffmpeg proxy failed"
    return True, ""
