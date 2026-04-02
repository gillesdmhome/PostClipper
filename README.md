# PostClipper

Semi-automated ingestion (YouTube, Twitch, uploads), transcription, clip suggestions, vertical rendering, review UI, and publish/export handoff for TikTok, Instagram Reels, and YouTube Shorts.

## Prerequisites

- **Python 3.10+**
- **Node.js 18+** (includes `npm`). Install from [nodejs.org](https://nodejs.org) or: `winget install OpenJS.NodeJS.LTS`
- **ffmpeg** and **ffprobe** (Windows: `winget install Gyan.FFmpeg`). If the API is started from the IDE and still cannot find them, set **`FFMPEG_PATH`** and **`FFPROBE_PATH`** in `backend/.env` to the full paths of `ffmpeg.exe` and `ffprobe.exe` (see `backend/.env.example`).
- **yt-dlp** is installed via `backend/requirements.txt`
- Optional ML stack (recommended): **`pip install -r requirements-ml.txt`** — installs **faster-whisper** (real ASR; avoids placeholder transcript text) and **sentence-transformers** (set **`SUGGEST_ENGINE=embeddings`** in `backend/.env`). After installing, **re-run transcribe / generate clips** on a job so the DB is not stuck on old placeholder segments.

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
# Optional ML: pip install -r requirements-ml.txt
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

## URLs you will use (dev)

- **Frontend UI**: `http://localhost:5173`
- **Backend API**: `http://127.0.0.1:8000`
- **Health check**: `GET /health` (example: `http://127.0.0.1:8000/health`)

If you can open `http://localhost:5173` but not `http://127.0.0.1:5173`, ensure Vite is bound to IPv4. In `frontend/vite.config.ts`, set `server.host = "0.0.0.0"` and restart `npm run dev`.

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

## How to use the API (examples)

### Start a new ingest

- **YouTube**

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/youtube ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.youtube.com/watch?v=VIDEO_ID\"}"
```

- **Twitch**

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/twitch ^
  -H "Content-Type: application/json" ^
  -d "{\"url\":\"https://www.twitch.tv/videos/VIDEO_ID\"}"
```

- **Upload a file**

```bash
curl -X POST http://127.0.0.1:8000/api/ingest/upload ^
  -F "file=@C:\\path\\to\\video.mp4"
```

All ingest endpoints return `{ "job_id": "...", "status": "pending" }` and then work continues in the background. Open the UI and navigate to `/job/{job_id}` to watch progress/logs.

### Generate clips (main workflow)

After ingest is finished (the job has a mezzanine), queue the pipeline:

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/JOB_ID/generate-clips -H "Content-Type: application/json" -d "{}"
```

This queues: **transcribe (if needed) → suggest clips → render drafts**.

### Inspect status + logs

```bash
curl http://127.0.0.1:8000/api/jobs
curl http://127.0.0.1:8000/api/jobs/JOB_ID
```

### Media preview URLs

- Proxy preview: `GET /api/jobs/{job_id}/media/proxy`\n+- Mezzanine: `GET /api/jobs/{job_id}/media/mezzanine`\n+- Draft per candidate: `GET /api/candidates/{candidate_id}/media/draft`

### YouTube downloads (403 / cookies)

If ingest from YouTube fails with HTTP 403 or cookie errors: copy `backend/.env.example` to `backend/.env`, set **`YTDLP_COOKIES_FILE`** to a Netscape-format `cookies.txt` exported while logged into YouTube, or **`YTDLP_COOKIES_FROM_BROWSER=firefox`**. On Windows, **Chrome/Edge** often hit DPAPI decrypt errors with `--cookies-from-browser`; use a file export instead. Details: `docs/platforms.md`.

### Windows: FFmpeg not found (WinError 2)

1. Install FFmpeg (includes ffprobe), e.g. `winget install Gyan.FFmpeg`.
2. Ensure **`backend/.env`** sets **`FFMPEG_PATH`** and **`FFPROBE_PATH`** to the full paths of `ffmpeg.exe` and `ffprobe.exe` (same `bin` folder). The app always reads **`backend/.env`** from the backend directory, not the shell cwd.
3. Optional: from `backend`, run `powershell -ExecutionPolicy Bypass -File scripts\print-ffmpeg-paths.ps1` (or `pwsh -File ...`) to print ready-to-paste lines.
4. Restart the API. Check **`GET /health`**: `ffmpeg_ok` should be `true`, and `ffmpeg` / `ffprobe` should show resolved paths. The server log on startup also prints the chosen FFmpeg path.

## License

MIT
