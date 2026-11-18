# Apokolips Search

A web-search experience by Apokolips. Level 1 uses the Brave Search API to display live web results through an Apokolips-designed interface. The Apokolips Spider crawler and first-party SQLite index remain separate components for later stages.

## Current status

**Level 1 — Basic Web Search (Brave Search API integration).**\n\nThe frontend now uses the server-side Brave Web Search proxy for web results. The API key remains on the backend, results are returned transiently, and provider responses are not written to the local index. The earlier first-party developer API remains available separately.

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation.
- Phase 02: Apokolips Spider crawler with robots.txt policy checks, sitemap discovery, safe URL handling, and bounded fetching.
- Phase 03: SQLite crawl metadata, FTS5 indexing, weighted BM25 ranking, search API, and connected React results page.
- Phase 04: durable SQLite crawl queue, background worker, leases, restart recovery, retries, and job management.
- Phase 05: API-key authenticated public search endpoint, per-key rate limits, administrator-only key management, public-mode protections, and developer documentation.

## Project structure

- `frontend/` — React + Vite search experience
- `backend/` — FastAPI API, crawler, SQLite store/queue, API-key management, and FTS5 index
- `crawler/` — crawler behaviour and operating documentation
- `indexer/` — future standalone indexing pipeline
- `docs/` — architecture, local setup, and public API documentation

## Quick start

### Backend

    cd backend
    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

### Frontend

In a second terminal:

    cd frontend
    npm install
    npm run dev

Open http://127.0.0.1:5173. API documentation is at http://127.0.0.1:8000/docs.

## Public Search API v1

- `GET /api/v1/search?q=...` — API-key authenticated search over the Apokolips first-party SQLite index.\n- `GET /api/v1/web-search?q=...` — Level 1 live web search through Brave; configured with the backend-only `BRAVE_SEARCH_API_KEY`.
- `POST /admin/api-keys` — create a developer key (administrator bearer token required).
- `GET /admin/api-keys` — list key metadata without secrets.
- `DELETE /admin/api-keys/{key_id}` — revoke a key.
- `GET /health` — API and search database health.

New developer keys default to 60 requests/minute; administrators may set 1–600 requests/minute. API keys are high-entropy random secrets; only SHA-256 hashes are stored and the complete key is shown once. See [Public API v1 documentation](docs/public-api.md) for authentication, examples, rate-limit headers, and deployment configuration.

Set `APOKOLIPS_PUBLIC_MODE=true` and a unique `APOKOLIPS_ADMIN_TOKEN` (at least 32 characters) before deploying publicly. In public mode, crawler operations and operational endpoints require the administrator token, and the old unauthenticated `/search` route is disabled. Configure exact browser origins with `APOKOLIPS_CORS_ORIGINS`. Never expose keys in frontend code or commit secrets.

## Crawler and local index

- `POST /crawl` — run a bounded crawl immediately.
- `POST /crawl/jobs` — enqueue a background crawl (HTTP 202).
- `GET /crawl/jobs` and `GET /crawl/jobs/{job_id}` — inspect job state.
- `POST /crawl/jobs/{job_id}/cancel` — cancel a pending job.
- `GET /stats`, `GET /crawl/runs`, and `GET /crawl/runs/{run_id}` — operational data (administrator-only in public mode).

The database is created at `backend/data/apokolips-search.sqlite3`; override it with `APOKOLIPS_DB_PATH`. Keep the database on persistent storage when hosted. The initial public deployment model is a single API instance using one persistent SQLite database; it is not yet a distributed or horizontally scaled service.

## Level 1 web search provider setup\n\nSet `BRAVE_SEARCH_API_KEY` on the backend and optionally set `BRAVE_SEARCH_COUNTRY=LK`. Never expose the key through a `VITE_*` variable or browser bundle. See [Level 1 Web Search](docs/level-1-web-search.md) for setup, API behaviour, privacy and provider-term notes. Brave requires an activated plan; check current pricing and usage in its dashboard before public release.\n\n## Search design and current limits

The first-party index remains a separate feature. SQLite FTS5 provides Unicode full-text matching and weighted BM25 ranking: title 20, description 3, headings 5, body 1. Search terms use AND semantics. The index contains only pages that Apokolips has actually crawled and stored; it is not a copy of the entire web. Image, video, and news search are not implemented.

## Validation

GitHub Actions checks Python 3.11 and 3.12 (Ruff plus backend tests) and builds the frontend with Node.js 22. Tests use temporary databases and mocked crawler output; they do not crawl live sites.

## Responsible crawling

Respect robots.txt, applicable site terms, access restrictions, and publisher preferences. Crawl only sites you are authorized to crawl. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. See [crawler documentation](crawler/README.md).
