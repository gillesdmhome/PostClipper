from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.services.ffmpeg_util import (
    ffprobe_duration_seconds,
    make_proxy,
    normalize_to_mezzanine,
    resolve_ffmpeg_ffprobe,
)


def ensure_dirs(job_id: str) -> dict[str, Path]:
    base = settings.data_dir / "jobs" / job_id
    return {
        "base": base,
        "raw": base / "raw",
        "mezzanine": base / "mezzanine",
        "proxy": base / "proxy",
        "drafts": base / "drafts",
        "exports": base / "exports",
        "transcripts": base / "transcripts",
    }


def _ytdlp_argv() -> list[str]:
    """Use standalone binary if on PATH; otherwise same Python as the API (pip install yt-dlp)."""
    if shutil.which("yt-dlp") or shutil.which("yt-dlp.exe"):
        return ["yt-dlp"]
    return [sys.executable, "-m", "yt_dlp"]


def _is_youtube_url(url: str) -> bool:
    u = url.lower()
    return "youtube.com" in u or "youtu.be" in u


def _ytdlp_cookie_variants() -> list[list[str]]:
    """
    Separate yt-dlp runs per variant. Do not pass --cookies and --cookies-from-browser
    together: Chromium on Windows often fails DPAPI decrypt for the browser DB (#10927).
    Order: file export first (no DPAPI), then browser, then no cookies (player_client retries may still work).
    """
    variants: list[list[str]] = []
    if settings.ytdlp_cookies_file and settings.ytdlp_cookies_file.is_file():
        variants.append(["--cookies", str(settings.ytdlp_cookies_file.resolve())])
    if settings.ytdlp_cookies_from_browser:
        b = settings.ytdlp_cookies_from_browser.strip()
        if b:
            variants.append(["--cookies-from-browser", b])
    if not variants:
        variants.append([])
    else:
        variants.append([])
    return variants


def _stderr_suggests_dpapi_cookie_failure(err: str) -> bool:
    e = err.lower()
    return "dpapi" in e or "failed to decrypt" in e


def _ytdlp_subprocess_env() -> dict[str, str] | None:
    """Prepend discovered ffmpeg dir so yt-dlp can merge formats without relying on PATH."""
    ff, _ = resolve_ffmpeg_ffprobe()
    if not ff:
        return None
    env = os.environ.copy()
    bin_dir = str(Path(ff).resolve().parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    return env


def _ytdlp_ffmpeg_location_args() -> list[str]:
    """Tell yt-dlp exactly where ffmpeg lives (more reliable than PATH on Windows)."""
    ff, _ = resolve_ffmpeg_ffprobe()
    if not ff:
        return []
    loc = str(Path(ff).resolve().parent)
    return ["--ffmpeg-location", loc]


def _youtube_download_attempts() -> list[list[str]]:
    """
    YouTube's default web client often yields SABR-only formats and HTTP 403 on segment URLs.
    Try non-web player clients first, then broader format fallbacks.
    See: https://github.com/yt-dlp/yt-dlp/issues/12482
    """
    return [
        [
            "--extractor-args",
            "youtube:player_client=android,ios,tv_embedded",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
        ],
        [
            "--extractor-args",
            "youtube:player_client=web_creator,mweb",
            "-f",
            "bv*+ba/b",
            "--merge-output-format",
            "mp4",
        ],
        [
            "-f",
            "bestvideo*+bestaudio/best",
            "--merge-output-format",
            "mp4",
        ],
    ]


def download_with_ytdlp(url: str, out_dir: Path, out_template: str = "source") -> tuple[bool, Path | None, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{out_template}.%(ext)s"
    cookie_variants = _ytdlp_cookie_variants()
    ytdlp_bin = _ytdlp_argv()

    if _is_youtube_url(url):
        attempt_suffixes = _youtube_download_attempts()
    else:
        attempt_suffixes = [["-f", "bv*+ba/b", "--merge-output-format", "mp4"]]

    ytdlp_env = _ytdlp_subprocess_env()
    last_err = ""
    for suffix in attempt_suffixes:
        for cookies in cookie_variants:
            argv = (
                ytdlp_bin
                + _ytdlp_ffmpeg_location_args()
                + cookies
                + suffix
                + ["-o", str(out_path), url]
            )
            try:
                p = subprocess.run(
                    argv,
                    capture_output=True,
                    text=True,
                    timeout=7200,
                    env=ytdlp_env,
                )
            except FileNotFoundError:
                return (
                    False,
                    None,
                    "yt-dlp not found. Install: pip install -U yt-dlp (same venv as API) or add yt-dlp to PATH.",
                )
            except subprocess.TimeoutExpired:
                return False, None, "yt-dlp timed out"
            if p.returncode == 0:
                files = sorted(out_dir.glob(f"{out_template}.*"), key=lambda x: x.stat().st_mtime, reverse=True)
                if files:
                    return True, files[0], ""
                last_err = "No output file from yt-dlp"
                continue
            err = (p.stderr or p.stdout or "yt-dlp failed")[-8000:]
            if "No module named" in err and "yt_dlp" in err:
                return (
                    False,
                    None,
                    "yt-dlp Python module missing. Run: pip install -U yt-dlp",
                )
            last_err = err
            if _stderr_suggests_dpapi_cookie_failure(err) and any(
                a == "--cookies-from-browser" for a in cookies
            ):
                continue

    hint = ""
    has_cookie_file = bool(settings.ytdlp_cookies_file and settings.ytdlp_cookies_file.is_file())
    if _is_youtube_url(url) and "403" in last_err and not has_cookie_file:
        hint = (
            " For YouTube 403, set YTDLP_COOKIES_FILE to a Netscape cookies.txt while logged in, "
            "or YTDLP_COOKIES_FROM_BROWSER=firefox (Chrome/Edge on Windows often hit DPAPI; see yt-dlp #10927)."
        )
    elif _stderr_suggests_dpapi_cookie_failure(last_err):
        hint = (
            " Chrome/Edge cookie DB on Windows can fail DPAPI decrypt. Use YTDLP_COOKIES_FILE (exported cookies.txt), "
            "try YTDLP_COOKIES_FROM_BROWSER=firefox, or leave cookie env unset. https://github.com/yt-dlp/yt-dlp/issues/10927"
        )
    return False, None, last_err + hint


def process_upload(src_path: Path, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    dest = raw_dir / src_path.name
    shutil.copy2(src_path, dest)
    return dest


def ingest_pipeline(job_id: str, raw_file: Path) -> tuple[bool, str, dict]:
    dirs = ensure_dirs(job_id)
    mezz = dirs["mezzanine"] / "mezzanine.mp4"
    proxy = dirs["proxy"] / "proxy.mp4"

    ok, err = normalize_to_mezzanine(raw_file, mezz)
    if not ok:
        return False, err, {}

    ok_p, err_p = make_proxy(mezz, proxy)
    if not ok_p:
        return False, err_p, {}

    duration = ffprobe_duration_seconds(mezz)
    return True, "", {
        "mezzanine_path": str(mezz.resolve()),
        "proxy_path": str(proxy.resolve()),
        "duration_seconds": duration,
    }
