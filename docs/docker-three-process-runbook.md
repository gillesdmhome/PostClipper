# Runbook: three-process stack with Docker

This document lists **every step** to run PostClipper as **frontend (host) + website API (container) + video worker (container)**, with Redis and Postgres from Compose.

## What you are running

| # | Process | How (this runbook) |
|---|---------|-------------------|
| 1 | **Frontend** | Node on your machine — `npm run dev` in `frontend/` |
| 2 | **Website API** | Docker service `api` — FastAPI on port **8000** |
| 3 | **Video worker** | Docker service `worker` — Arq, FFmpeg, yt-dlp |
| + | **Redis** | Docker service `redis` — job queue |
| + | **Postgres** | Docker service `postgres` — database (required for multi-container; SQLite is not shared across containers) |

Python dependency layout (see [`backend/requirements.txt`](../backend/requirements.txt)):

- **`requirements-api.txt`** — API-only (FastAPI, SQLAlchemy, asyncpg, redis, arq, …); **no yt-dlp**.
- **`requirements-worker.txt`** — `-r requirements-api.txt` + **yt-dlp**; used by **`Dockerfile.worker`**.
- **`requirements.txt`** — `-r requirements-worker.txt` — **full local venv** (one install for dev).
- **`requirements-ml.txt`** — optional Whisper + sentence-transformers; **not** in default Docker worker image (extend image or install locally if needed).

---

## Prerequisites (host machine)

1. **Docker Desktop** (or Docker Engine + Compose v2) — `docker compose version` works.
2. **Node.js 18+** and **npm** — for the frontend.
3. **Ports free:** `8000` (API), `5173` (Vite), `5432` (Postgres), `6379` (Redis), or change mappings in [`docker-compose.yml`](../docker-compose.yml).
4. **Git clone** of the repo (or your working copy).

---

## Step 1 — Build and start backend stack

From the **repository root** (where `docker-compose.yml` lives):

```bash
docker compose build --no-cache
docker compose up -d
```

Wait until Postgres is healthy and containers are up:

```bash
docker compose ps
```

You should see `api`, `worker`, `redis`, `postgres` running (or `running` / `healthy`).

Compose waits for Postgres to pass **`pg_isready`** before starting `api` and `worker`, so they should not connect before the database accepts connections.

---

## Step 2 — Verify API and worker

**API health** (slim API skips FFmpeg check; `media_check_skipped` may be true):

```bash
curl -s http://127.0.0.1:8000/health
```

Expect `"status":"ok"` and `"job_queue":"redis"`.

**Worker logs** (should show Arq listening / processing, no crash loop):

```bash
docker compose logs worker --tail 80
```

**API logs** if something fails:

```bash
docker compose logs api --tail 80
```

---

## Step 3 — Start the frontend (host)

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. The Vite dev server proxies `/api` to **http://127.0.0.1:8000** (see `frontend/vite.config.ts`).

---

## Step 4 — Smoke test

1. In the UI, start a **YouTube** or **upload** ingest, or use `curl` against `http://127.0.0.1:8000` (see [README](../README.md)).
2. Confirm the **worker** picks up jobs: `docker compose logs worker -f` while ingesting.
3. After mezzanine exists, run **Generate clips** and wait for drafts.

---

## Environment (Compose defaults)

Already set in [`docker-compose.yml`](../docker-compose.yml) for `api` and `worker`:

| Variable | Value (in Compose) |
|----------|----------------------|
| `REDIS_URL` | `redis://redis:6379/0` |
| `DATABASE_URL` | `postgresql+asyncpg://postclipper:postclipper@postgres:5432/postclipper` |
| `DATA_DIR` | `/data` (volume `postclipper_media`) |
| `API_SKIP_MEDIA_CHECK` | `true` on **api** only |

Optional: **YouTube cookies / OAuth** — set vars in repository [`.env`](../.env) or mount **`backend/.env`** / secrets into **both** `api` and `worker` if you use those features.

---

## Uploads and shared storage

`POST /api/ingest/upload` writes files into **`DATA_DIR` on the API container**. The **worker** must see the same files — Compose mounts **`postclipper_media:/data`** on **both** `api` and `worker`. Do not run only one service with `/data` unless you change the design.

---

## Troubleshooting

| Symptom | Check |
|--------|--------|
| Worker idle, jobs stuck | `REDIS_URL` on API; `docker compose logs worker`; Redis reachable from containers. |
| API 500 on DB | Postgres healthy: `docker compose ps`; `docker compose logs postgres`. |
| Ingest OK, render fails | Worker image has **FFmpeg** (`Dockerfile.worker`); worker logs for ffmpeg errors. |
| CORS errors | `CORS_ORIGINS` in `api` includes your frontend origin (`http://localhost:5173`). |
| ML / Whisper missing | Default worker image does **not** install `requirements-ml.txt`; build a custom layer or run worker locally with ML venv. |

---

## Stop and clean

```bash
docker compose down
```

Remove volumes (deletes Postgres data and media):

```bash
docker compose down -v
```

---

## See also

- [deploy.md](deploy.md) — topology and env reference  
- [architecture.md](architecture.md) — three-process diagram  
- [README](../README.md) — local dev without Docker, API examples  
