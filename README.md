# Apokolips Search

An independent web search engine project by Apokolips. The search results shown by this project are sourced from its own crawler and local index, not from another search provider.

## Current status

**Phase 04 — Durable background crawl queue and worker reliability.**

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation.
- Phase 02: Apokolips Spider crawler with robots.txt policy checks, sitemap discovery, safe URL handling, and bounded fetching.
- Phase 03: SQLite crawl metadata, SQLite FTS5 indexing, weighted BM25 ranking, search API, and connected React results page.
- Phase 04: SQLite-backed crawl job queue, background worker, atomic job claiming, worker leases, restart recovery, bounded retries, and job status/cancellation endpoints.

## Project structure

- frontend/ — React + Vite search experience
- backend/ — FastAPI API, Apokolips Spider, SQLite store/queue, background worker, and FTS5 search index
- crawler/ — crawler behaviour and operating documentation
- indexer/ — future standalone indexing pipeline
- docs/ — architecture and local setup

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

## Main endpoints

- POST /crawl — run a bounded crawl immediately and persist results.
- POST /crawl/jobs — enqueue a bounded crawl for background processing; returns HTTP 202.
- GET /crawl/jobs — list recent crawl jobs.
- GET /crawl/jobs/{job_id} — inspect a job and its current state.
- POST /crawl/jobs/{job_id}/cancel — cancel a job only while it is pending.
- GET /search?q=... — search the local Apokolips index with BM25 ranking.
- GET /stats — database and index statistics.
- GET /crawl/runs — recent crawl history.
- GET /crawl/runs/{run_id} — one crawl run's status and metrics.
- GET /health — API, database, and FTS5 health check.

The queue and search index share the SQLite database created at backend/data/apokolips-search.sqlite3. Set APOKOLIPS_DB_PATH to choose another local path. The database is application data and is excluded from Git.

## Background queue behaviour

The API starts one lightweight worker when the application starts. Jobs are claimed atomically in SQLite, have a 180-second worker lease, and are recovered after an application restart. Failed jobs use bounded retries (three attempts by default) with short exponential backoff. A pending job can be cancelled; a running job cannot be force-stopped through the HTTP API. The direct POST /crawl endpoint remains available.

This is a local, single-process queue, not a distributed worker service or recurring cron scheduler. Keep the API bound to localhost and do not expose unauthenticated crawl-control endpoints publicly.

## Search design

The current local implementation uses SQLite FTS5 with Unicode tokenization and weighted BM25 field ranking: title 20, description 3, headings 5, and body 1. Search terms use AND semantics and results are paginated. Image, video, and news search verticals are not implemented yet.

## Validation

GitHub Actions checks Python 3.11 and 3.12 (Ruff plus backend tests) and builds the frontend with Node.js 22. Tests use temporary databases and mocked crawler output; they do not crawl live sites.

## Responsible crawling

Respect robots.txt, applicable site terms, access restrictions, and publisher preferences. Use the crawler only on sites you are authorized to crawl. It does not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. See crawler/README.md for its limits.
