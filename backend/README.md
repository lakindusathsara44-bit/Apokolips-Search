# Backend

FastAPI service for Apokolips Search: a Brave Search API proxy for Level 1 web search, plus Apokolips Spider, SQLite metadata and durable queue, FTS5/BM25 search, public API keys, and per-key quotas.

## Run locally

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health check: http://127.0.0.1:8000/health  
Interactive API docs: http://127.0.0.1:8000/docs

The SQLite database is created at `backend/data/apokolips-search.sqlite3`. Override it with `APOKOLIPS_DB_PATH`.

## Public Search API v1

`GET /api/v1/search?q=...` requires an active key in `X-API-Key`. Results come from Apokolips' own FTS5 index, with title/description/headings/body weighted BM25 ranking. The public endpoint supports `page` (1–10,000) and `page_size` (1–20). Query length is 1–200 characters and at most 12 searchable words.

Keys default to 60 requests/minute; the administrator can configure 1–600 requests/minute per key. Each UTC-minute quota is updated atomically in SQLite. Rate-limit headers are `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`; HTTP 429 also includes `Retry-After`.

### Enable public mode

Set these environment variables before starting the application:

- `APOKOLIPS_PUBLIC_MODE=true`
- `APOKOLIPS_ADMIN_TOKEN` — secret with at least 32 characters; generate a new high-entropy value and keep it outside Git.
- `APOKOLIPS_CORS_ORIGINS` — optional comma-separated exact browser origins.
- `APOKOLIPS_DB_PATH` — optional persistent SQLite file path.

Public mode fails startup if the administrator token is missing or too short. In public mode, the legacy unauthenticated `/search` route is disabled. Crawl operations, crawl job/history endpoints, and statistics require the administrator bearer token. The API-key administration endpoints always require that token.

### Key management

- `POST /admin/api-keys` — create a key. JSON: `{"name":"My app","requests_per_minute":60}`.
- `GET /admin/api-keys` — list metadata only.
- `DELETE /admin/api-keys/{key_id}` — revoke a key.

Send `Authorization: Bearer YOUR_ADMIN_TOKEN`. The raw API key is returned only once. The database stores its SHA-256 hash, not the secret. Store the key in your server-side secret manager; do not commit it or embed it in browser JavaScript.

Example search:

    curl --get http://127.0.0.1:8000/api/v1/search ^
      -H "X-API-Key: aps_live_your_key" ^
      --data-urlencode "q=Apokolips search" ^
      --data-urlencode "page=1" ^
      --data-urlencode "page_size=10"

See [Public API v1](../docs/public-api.md) for complete requests, response format, errors, and production checklist.

## Level 1 web search provider

Set `BRAVE_SEARCH_API_KEY` in the backend process environment and optionally set `BRAVE_SEARCH_COUNTRY=LK`. The frontend calls `GET /api/v1/web-search?q=...&page=1&page_size=10`; the server calls Brave using `X-Subscription-Token`. The upstream key is never sent to the browser. Results are not cached or stored in the Apokolips index. A simple in-memory limit of 30 requests per client IP per minute protects a single backend process. See [Level 1 Web Search](../docs/level-1-web-search.md).

## Crawler endpoints

- `POST /crawl` — bounded synchronous crawl and indexing.
- `POST /crawl/jobs` — queue a background crawl (HTTP 202).
- `GET /crawl/jobs` and `GET /crawl/jobs/{job_id}` — job status.
- `POST /crawl/jobs/{job_id}/cancel` — cancel pending jobs.
- `GET /stats`, `GET /crawl/runs`, `GET /crawl/runs/{run_id}` — index and crawl operations.

The worker uses a 180-second lease and retries failed jobs up to three times. The queue is local and single-process, not a distributed queue or recurring scheduler. For public deployment, use one API instance with a persistent database volume, HTTPS termination, and protected administrator configuration. Do not expose the unauthenticated local crawler mode to the internet.

## Test and lint

    python -m pytest -q
    python -m ruff check app tests

Tests use temporary SQLite databases and mocked crawler output; they do not initiate live external crawls.
