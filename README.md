# Clip Social Pipeline

Semi-automated ingestion (YouTube, Twitch, uploads), transcription, clip suggestions, vertical rendering, review UI, and publish/export handoff for TikTok, Instagram Reels, and YouTube Shorts.

## Prerequisites

- **Python 3.10+** (required for a clean yt-dlp experience; 3.9 shows deprecation warnings)
- **Node.js 18+** (includes `npm`). Install from [nodejs.org](https://nodejs.org) or: `winget install OpenJS.NodeJS.LTS`
- **ffmpeg** and **ffprobe** (Windows: `winget install Gyan.FFmpeg`). If the API is started from the IDE and still cannot find them, set **`FFMPEG_PATH`** and **`FFPROBE_PATH`** in `backend/.env` to the full paths of `ffmpeg.exe` and `ffprobe.exe` (see `backend/.env.example`).
- **yt-dlp** on PATH (for YouTube/Twitch VOD download)
- Optional ML stack (recommended): **`pip install -r requirements-ml.txt`** — installs **faster-whisper** (real ASR; avoids placeholder transcript text) and **sentence-transformers** (set **`SUGGEST_ENGINE=embeddings`** in `backend/.env`). After installing, **re-run transcribe / generate clips** on a job so the DB is not stuck on old placeholder segments.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# Optional: pip install faster-whisper torch
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` — API proxied to `http://localhost:8000`.

If your terminal was opened **before** Node was installed and `node` / `npm` are not found, either **restart the terminal/IDE** or from the repo root run:

```powershell
.\dev-frontend.ps1
```

## API overview

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ingest/youtube` | Body: `{"url": "..."}` |
| POST | `/api/ingest/twitch` | Body: `{"url": "..."}` |
| POST | `/api/ingest/upload` | Multipart file (Zoom/podcast) |
| POST | `/api/jobs/{id}/transcribe` | Run ASR on mezzanine |
| POST | `/api/jobs/{id}/suggest-clips` | Generate candidates |
| POST | `/api/jobs/{id}/render` | Render vertical drafts |
| GET | `/api/jobs` | List jobs + status |
| GET | `/api/jobs/{id}` | Job detail, candidates, transcript |
| PATCH | `/api/candidates/{id}` | Update trim/caption text |
| POST | `/api/candidates/{id}/publish` | Queue publish (YouTube if configured, else export bundle) |

Set `YOUTUBE_CLIENT_SECRETS_PATH` and complete OAuth flow for direct Shorts upload (see `docs/platforms.md`).

### YouTube downloads (403 / cookies)

If ingest from YouTube fails with HTTP 403 or cookie errors: copy `backend/.env.example` to `backend/.env`, set **`YTDLP_COOKIES_FILE`** to a Netscape-format `cookies.txt` exported while logged into YouTube, or **`YTDLP_COOKIES_FROM_BROWSER=firefox`**. On Windows, **Chrome/Edge** often hit DPAPI decrypt errors with `--cookies-from-browser`; use a file export instead. Details: `docs/platforms.md`.

### Windows: FFmpeg not found (WinError 2)

1. Install FFmpeg (includes ffprobe), e.g. `winget install Gyan.FFmpeg`.
2. Ensure **`backend/.env`** sets **`FFMPEG_PATH`** and **`FFPROBE_PATH`** to the full paths of `ffmpeg.exe` and `ffprobe.exe` (same `bin` folder). The app always reads **`backend/.env`** from the backend directory, not the shell cwd.
3. Optional: from `backend`, run `powershell -ExecutionPolicy Bypass -File scripts\print-ffmpeg-paths.ps1` (or `pwsh -File ...`) to print ready-to-paste lines.
4. Restart the API. Check **`GET /health`**: `ffmpeg_ok` should be `true`, and `ffmpeg` / `ffprobe` should show resolved paths. The server log on startup also prints the chosen FFmpeg path.

## License

MIT
