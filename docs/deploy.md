# Deploying PostClipper

## Three-process topology

1. **Frontend** — `cd frontend && npm run dev` (or build static assets behind nginx).
2. **Website API** — `uvicorn app.main:app` from `backend/` with [`requirements-api.txt`](../backend/requirements-api.txt) optional slim install; set **`API_SKIP_MEDIA_CHECK=true`** when FFmpeg is not installed on the API host.
3. **Video worker** — `arq app.worker.WorkerSettings` from `backend/` with [`requirements-worker.txt`](../backend/requirements-worker.txt) (includes yt-dlp); **FFmpeg + ffprobe** required on the worker.

**`REDIS_URL`** must be set on both API and worker for split deploy (API enqueues, worker consumes). Without Redis, the API falls back to in-process `BackgroundTasks` (dev only).

## Trigger.dev (optional)

Use [Trigger.dev](https://trigger.dev/) so the API only performs a fast HTTPS call to their API to start a run; a Trigger task then **POSTs** to your app’s relay, which enqueues the same Arq jobs as before. Heavy work still runs on your **PostClipper worker** (Redis + `arq`); Trigger is an orchestration hop, not a replacement for FFmpeg/yt-dlp on your infra.

1. Create a project at [cloud.trigger.dev](https://cloud.trigger.dev/) and copy **Secret API key** (`tr_dev_…` / `tr_prod_…`).
2. Repo root: edit [`.env`](../.env) — set **`TRIGGER_PROJECT_REF`**, **`TRIGGER_SECRET_KEY`**, **`POSTCLIPPER_EXECUTOR_URL`**, **`POSTCLIPPER_EXECUTOR_SECRET`**, and optional **`TRIGGER_RELAY_TASK_ID`** / **`POSTCLIPPER_RELAY_PATH`** / **`TRIGGER_API_BASE`**. Run `npm install`, then `npm run trigger:dev` (or `trigger:deploy` for production). The Trigger CLI loads repository `.env` via `dotenv`.
3. **FastAPI** loads **repository `.env` first**, then optional **`backend/.env`** (duplicate keys in `backend/.env` win).
4. In the Trigger.dev dashboard → **Environments** (for deployed runs), set the same **`POSTCLIPPER_EXECUTOR_*`** and optional path/task id vars as in `.env`.
5. Keep **`REDIS_URL`** on the API (relay enqueues to Redis). `GET /health` reports `job_queue`: `trigger_dev` when `TRIGGER_SECRET_KEY` is set.

**`TRIGGER_RELAY_TASK_ID`** must match between [`trigger/postclipper.ts`](../trigger/postclipper.ts) and the API ([`backend/app/trigger_client.py`](../backend/app/trigger_client.py)). **`POSTCLIPPER_RELAY_PATH`** must match the mounted relay route (`POSTCLIPPER_RELAY_PATH` / `postclipper_relay_path` on the API).

## Docker Compose (API + worker + Redis + Postgres)

From the **repository root**:

```bash
docker compose up -d --build
```

Step-by-step checklist (prereqs, verification, frontend, troubleshooting): **[docker-three-process-runbook.md](docker-three-process-runbook.md)**.

Services:

- `api` — port **8000**, `API_SKIP_MEDIA_CHECK=true`, mounts **`postclipper_media`** at `/data`.
- `worker` — same DB, Redis, and **`/data`** volume (required so ingest/render files match DB paths).
- `redis`, `postgres` — as defined in [`docker-compose.yml`](../docker-compose.yml).

Example env inside compose (already set for `api` / `worker`):

```env
REDIS_URL=redis://redis:6379/0
DATABASE_URL=postgresql+asyncpg://postclipper:postclipper@postgres:5432/postclipper
DATA_DIR=/data
```

Run the **frontend** on the host with `VITE` proxy to `http://127.0.0.1:8000`, or add a static frontend service later.

## Shared `DATA_DIR` (upload path)

`POST /api/ingest/upload` **streams the file on the API process** into `DATA_DIR`. The worker then reads that path. In Docker, **both containers must mount the same volume** at `DATA_DIR` (Compose does this via `postclipper_media`).

For presigned uploads straight to object storage (API does not receive bytes), a future change would enqueue object keys to the worker instead.

## Local Python (no Docker)

```bash
cd backend
python -m venv .venv
# Full stack in one venv:
pip install -r requirements.txt
# Or API-only tooling:
# pip install -r requirements-api.txt
```

Terminal 1 — API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Terminal 2 — worker (requires `REDIS_URL`):

```bash
arq app.worker.WorkerSettings
```

## Environment variables

| Variable | Role |
|----------|------|
| `REDIS_URL` | Enqueue to Arq; worker **must** run when set. |
| `DATABASE_URL` | Defaults to SQLite under `backend/data/`. Use Postgres for Compose multi-service. |
| `DATA_DIR` | Job media root (env maps to `data_dir` in config). |
| `API_SKIP_MEDIA_CHECK` | If `true`, API skips FFmpeg discovery and `/health` reports `media_check_skipped`. |
| `TRIGGER_SECRET_KEY` | Optional. If set, enqueue goes through [Trigger.dev](https://trigger.dev/) (see Trigger.dev section). Requires `REDIS_URL` and `POSTCLIPPER_EXECUTOR_SECRET`. |
| `TRIGGER_PROJECT_REF` | Trigger.dev project ref (CLI + `.env` at repo root). |
| `TRIGGER_RELAY_TASK_ID` | Default `postclipper-relay`; must match the task id in `trigger/postclipper.ts`. |
| `POSTCLIPPER_EXECUTOR_SECRET` | Shared secret for header `X-PostClipper-Executor-Secret` (Trigger task → API). |
| `POSTCLIPPER_EXECUTOR_URL` | Base URL of the FastAPI app (no path); used by the Trigger task. |
| `POSTCLIPPER_RELAY_PATH` | Default `/internal/trigger-dev/relay`; API field `postclipper_relay_path`. |
| `TRIGGER_API_BASE` | Default `https://api.trigger.dev`. |

Use repository [`.env`](../.env) for defaults; add **`backend/.env`** only for local overrides (gitignored).

## Health check

`GET /health` returns `job_queue`: `redis` or `in_process`, and either resolved FFmpeg paths or `media_check_skipped` when the slim API flag is on.

## Multi-worker caveat

Pipeline coordination uses an in-process `asyncio.Lock` in `bg_tasks`. With **multiple worker replicas**, use **one worker** per deployment or add a **Redis lock** before scaling workers.

## Schema migrations

The app uses `create_all` on startup. For production schema evolution, add Alembic (or similar).
