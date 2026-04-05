# Platform constraints & setup

## YouTube Shorts (optional direct upload)

1. Create a Google Cloud OAuth client (Desktop app) and download JSON as client secrets.
2. Set environment variable or `.env`:
   - `YOUTUBE_CLIENT_SECRETS_PATH=/path/to/client_secret.json`
   - Optional: `YOUTUBE_TOKEN_PATH=/path/to/youtube_token.json`
3. Install deps: `pip install google-api-python-client google-auth-oauthlib google-auth-httplib2`
4. First upload triggers a local browser OAuth flow; token is cached for later uploads.

Upload uses YouTube Data API v3 `videos.insert`. Titles/descriptions must respect YouTube limits.

## TikTok & Instagram Reels

Direct posting APIs are restricted or partner-only. This pipeline generates a **ZIP export** (`clip.mp4` + `metadata.json`) per publish job.

1. Call `POST /api/candidates/{id}/publish` with `platform: "tiktok"` or `instagram_reels"`.
2. Poll job detail or list publish jobs from candidate; when status is `export_ready`, download:
   - `GET /api/publish-jobs/{publish_job_id}/download`

Upload the zip contents manually or via a scheduler (Metricool, Buffer, etc.).

## ffmpeg / yt-dlp

- **ffmpeg** and **ffprobe** are required for mezzanine, proxy, vertical renders, and yt-dlp merges.
- **`backend/.env`** is always loaded from the backend directory (not the shell’s current directory), so `FFMPEG_PATH` applies even if you start uvicorn from the repo root.
- The backend resolves binaries in this order: **`FFMPEG_PATH` / `FFPROBE_PATH`** in `.env`, then the process **`PATH`**, then on **macOS/Linux** **`/opt/homebrew/bin`** and **`/usr/local/bin`** when `PATH` is minimal (typical GUI/IDE launches), then on **Windows** the **machine + user `Path` from the registry** (so winget/user installs work even when Cursor/IDE starts Python with a minimal `PATH`), then known locations (**WinGet** packages, **Program Files**, **Scoop**, **Chocolatey**). **`ffprobe`** is usually resolved next to **`ffmpeg`** in the same directory.
- **yt-dlp** is pulled in via `pip install -r requirements.txt`; the app runs it as `python -m yt_dlp` if the `yt-dlp` executable is not on `PATH`. When ffmpeg is discovered, its directory is prepended to `PATH` for yt-dlp subprocesses, and **`--ffmpeg-location`** is passed so merges still work.
- **`GET /health`** returns **`ffmpeg_ok`** plus resolved **`ffmpeg`** / **`ffprobe`** paths (or `null`) for quick checks. On Windows, from **`backend`**, run **`powershell -ExecutionPolicy Bypass -File scripts/print-ffmpeg-paths.ps1`** to print `.env` lines.
- **Python 3.12+** is recommended (latest stable is fine). Use **SQLAlchemy ≥2.0.45** on **Python 3.14+** (see `backend/requirements.txt`).
- Respect site Terms of Service; prefer uploading your own files when in doubt.

### YouTube 403 / SABR (“unable to download video data”)

YouTube often blocks the default **web** client (SABR-only formats, HTTP 403). This app retries with **android / ios / tv_embedded**, then **web_creator / mweb**, then a generic **best** merge.

If downloads still fail:

1. **Use Python 3.12+** for the backend venv, then **`pip install -U yt-dlp`** (consider a [nightly build](https://github.com/yt-dlp/yt-dlp/wiki/Installation) if YouTube still breaks).
2. **Cookies** (while logged into YouTube), in `.env` next to the backend:
   - **Preferred on Windows:** export a Netscape `cookies.txt` and set `YTDLP_COOKIES_FILE=C:\path\to\cookies.txt` (avoids DPAPI issues).
   - **`--cookies-from-browser`:** `firefox` usually works on Windows; **Chrome / Edge** often hit **“Failed to decrypt with DPAPI”** ([yt-dlp #10927](https://github.com/yt-dlp/yt-dlp/issues/10927)) — use a file export or Firefox instead.

The downloader tries a cookies file first, then browser, then no cookies so a DPAPI failure on Edge/Chrome does not block the run entirely.

See [yt-dlp #12482](https://github.com/yt-dlp/yt-dlp/issues/12482) for background on SABR / client changes.
