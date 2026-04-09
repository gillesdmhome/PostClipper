# Runbook: full stack with Docker

This document lists **every step** to run PostClipper with **Compose**: **web UI (nginx + static build)**, **website API**, **video worker**, **Redis**, and **Postgres**. You can still run the **frontend on the host** with Vite for hot reload (see Step 3).

## What you are running

| # | Process | How (default Compose) |
|---|---------|-------------------|
| 1 | **Frontend UI** | Docker service **`web`** — nginx on host port **5173**, proxies `/api` to **`api`** |
| 2 | **Website API** | Docker service **`api`** — FastAPI on host port **8001** (container **8000**) |
| 3 | **Video worker** | Docker service **`worker`** — Arq, FFmpeg, yt-dlp |
| + | **Redis** | Docker service **`redis`** — job queue |
| + | **Postgres** | Docker service **`postgres`** — database (required for multi-container; SQLite is not shared across containers) |

Python dependency layout (see [`backend/requirements.txt`](../backend/requirements.txt)):

- **`requirements-api.txt`** — API-only (FastAPI, SQLAlchemy, asyncpg, redis, arq, …); **no yt-dlp**.
- **`requirements-worker.txt`** — `-r requirements-api.txt` + **yt-dlp**; used by **`Dockerfile.worker`**.
- **`requirements.txt`** — `-r requirements-worker.txt` — **full local venv** (one install for dev).
- **`requirements-ml.txt`** — optional Whisper + sentence-transformers; **not** in default Docker worker image (extend image or install locally if needed).

---

## Prerequisites (host machine)

1. **Docker Desktop** (or Docker Engine + Compose v2) — `docker compose version` works.
2. **Node.js 18+** and **npm** — only if you run the **host** Vite dev server (Step 3, optional).
3. **Ports free:** `8001` (API on host), `5173` (**web** UI), `5432` (Postgres), `6379` (Redis), or change mappings in [`docker-compose.yml`](../docker-compose.yml).
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

You should see `web`, `api`, `worker`, `redis`, `postgres` running (or `running` / `healthy`).

Compose waits for Postgres to pass **`pg_isready`** before starting `api` and `worker`, so they should not connect before the database accepts connections.

---

## Step 2 — Verify API and worker

**API health** (slim API skips FFmpeg check; `media_check_skipped` may be true):

```bash
curl -s http://127.0.0.1:8001/health
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

## Step 3 — Frontend

**Default (included in `docker compose up`):** open **http://localhost:5173**. The **`web`** container serves the built SPA and proxies **`/api`** to the **`api`** service on the Docker network (same-origin; no CORS setup needed for the browser).

**Optional — hot reload on the host:** stop the **`web`** service if port 5173 conflicts (`docker compose stop web`), then:

```bash
cd frontend
npm install
npm run dev
```

Set **`VITE_API_TARGET=http://127.0.0.1:8001`** when the API runs in Compose (see `frontend/vite.config.ts`). Without it, Vite defaults to port **8000**.

---

## Step 4 — Smoke test

1. In the UI, start a **YouTube** or **upload** ingest, or use `curl` against `http://127.0.0.1:8001` (see [README](../README.md)).
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
