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

# Single troubleshooting pointer for logs, API warnings, and FileNotFoundError (keep in sync with README).
FFMPEG_SETUP_HINT = (
    "Install ffmpeg and ffprobe on the system, confirm GET /health shows ffmpeg_ok. "
    "Details: README Prerequisites and docs/platforms.md (ffmpeg / yt-dlp). "
    "Override: FFMPEG_PATH and FFPROBE_PATH in backend/.env."
)


def _abs_tool_path(p: Path) -> Path:
    p = p.expanduser()
    return p if p.is_absolute() else (_BACKEND_DIR / p).resolve()


def _ffmpeg_tool_help() -> str:
    return f"FFmpeg/ffprobe not found. {FFMPEG_SETUP_HINT}"


def _windows_registry_path_directories() -> list[Path]:
    """
    PATH as stored in the registry (system then user). IDE-launched Python often inherits a minimal PATH;
    this matches what Explorer/cmd get after winget adds FFmpeg to the user PATH.
    """
    import winreg

    dirs: list[Path] = []

    def append_from_key(hive: int, subpath: str) -> None:
        try:
            with winreg.OpenKey(hive, subpath) as key:
                val, _ = winreg.QueryValueEx(key, "Path")
        except OSError:
            return
        if not val or not isinstance(val, str):
            return
        for segment in val.split(";"):
            expanded = os.path.expandvars(segment.strip())
            if not expanded:
                continue
            try:
                p = Path(expanded).resolve()
                if p.is_dir():
                    dirs.append(p)
            except OSError:
                continue

    # Windows merges PATH as system directories first, then user (see MS docs on user path).
    append_from_key(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")
    append_from_key(winreg.HKEY_CURRENT_USER, r"Environment")
    return dirs


def _find_exe_in_directories(directories: list[Path], name: str) -> Path | None:
    for d in directories:
        cand = d / name
        try:
            if cand.is_file():
                return cand.resolve()
        except OSError:
            continue
    return None


def _probe_name() -> str:
    return "ffprobe.exe" if sys.platform == "win32" else "ffprobe"


def _resolved_ffprobe_sibling(ffmpeg_path: str) -> str | None:
    """ffprobe lives next to ffmpeg; resolve symlinks (e.g. WinGet Links\\ffmpeg.exe → real bin)."""
    try:
        parent = Path(ffmpeg_path).resolve(strict=False).parent
        sib = parent / _probe_name()
        if sib.is_file():
            return str(sib.resolve())
    except OSError:
        pass
    return None


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
            try:
                for d in pkgs.iterdir():
                    if not d.is_dir():
                        continue
                    # Any winget FFmpeg package (Gyan, BtbN, etc.) — folder name contains FFMPEG.
                    if "FFMPEG" not in d.name.upper():
                        continue
                    try:
                        for p in d.rglob("ffmpeg.exe"):
                            found.append(p)
                            break
                    except OSError:
                        continue
            except OSError:
                pass
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pffb = Path(pf) / "ffmpeg" / "bin" / "ffmpeg.exe"
    if pffb.is_file():
        found.append(pffb)
    # Common manual zip layout (installer usually matches ProgramFiles\ffmpeg\bin above)
    c_ffmpeg = Path(r"C:\ffmpeg\bin\ffmpeg.exe")
    if c_ffmpeg.is_file():
        found.append(c_ffmpeg)
    # Scoop default layout
    profile = os.environ.get("USERPROFILE", "")
    if profile:
        scoop = Path(profile) / "scoop" / "apps" / "ffmpeg" / "current" / "bin" / "ffmpeg.exe"
        if scoop.is_file():
            found.append(scoop)
    choco = Path(os.environ.get("ChocolateyInstall", r"C:\ProgramData\chocolatey"))
    choco_bin = choco / "bin" / "ffmpeg.exe"
    if choco_bin.is_file():
        found.append(choco_bin)
    for rel in (
        "lib/ffmpeg/tools/ffmpeg/bin/ffmpeg.exe",
        "lib/ffmpeg-full/tools/ffmpeg/bin/ffmpeg.exe",
    ):
        p = choco / rel
        if p.is_file():
            found.append(p)
    # De-dupe by resolved path while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    probe = _probe_name()
    for p in found:
        try:
            key = str(p.resolve())
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            out.append(p)
    # Drop candidates with no ffprobe beside resolved ffmpeg (WinGet Links symlinks, stray copies).
    paired: list[Path] = []
    for p in out:
        try:
            rp = p.resolve(strict=False)
            if (rp.parent / probe).is_file():
                paired.append(p)
        except OSError:
            continue
    return paired if paired else out


def _resolve_from_unix_common_bins() -> tuple[str | None, str | None]:
    """When PATH is minimal (e.g. IDE on macOS), Homebrew paths are often missing."""
    if sys.platform == "win32":
        return None, None
    ff: str | None = None
    fp: str | None = None
    for d in (Path("/opt/homebrew/bin"), Path("/usr/local/bin")):
        if not d.is_dir():
            continue
        try:
            ff_c = d / "ffmpeg"
            fp_c = d / "ffprobe"
            if ff is None and ff_c.is_file():
                ff = str(ff_c.resolve())
            if fp is None and fp_c.is_file():
                fp = str(fp_c.resolve())
        except OSError:
            continue
    return ff, fp


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

    if sys.platform != "win32" and (ff is None or fp is None):
        uff, ufp = _resolve_from_unix_common_bins()
        if ff is None and uff:
            ff = uff
        if fp is None and ufp:
            fp = ufp

    # Windows: PATH in the registry (winget/user installs) is often missing from IDE-inherited env.
    if sys.platform == "win32":
        reg_dirs = _windows_registry_path_directories()
        if ff is None:
            reg_ff = _find_exe_in_directories(reg_dirs, "ffmpeg.exe")
            if reg_ff is not None:
                ff = str(reg_ff)
        if fp is None:
            reg_fp = _find_exe_in_directories(reg_dirs, "ffprobe.exe")
            if reg_fp is not None:
                fp = str(reg_fp)

    if ff is None and sys.platform == "win32":
        for p in _iter_windows_ffmpeg_exes():
            ff = str(p.resolve(strict=False))
            break

    if fp is None and ff is not None:
        sib = _resolved_ffprobe_sibling(ff)
        if sib:
            fp = sib

    if fp is None and sys.platform == "win32":
        for p in _iter_windows_ffmpeg_exes():
            try:
                rp = str(p.resolve(strict=False))
            except OSError:
                continue
            sib = _resolved_ffprobe_sibling(rp)
            if sib:
                fp = sib
                if ff is None:
                    ff = rp
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
