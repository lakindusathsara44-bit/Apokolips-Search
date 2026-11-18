# Apokolips Search

An independent web search engine project by Apokolips. The search results shown by this project are sourced from its own crawler and local index, not from another search provider.

## Current status

**Phase 03 — Local persistent index and first-party ranked web search.**

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation.
- Phase 02: Apokolips Spider crawler with robots.txt policy checks, sitemap discovery, safe URL handling, and bounded fetching.
- Phase 03: SQLite crawl metadata, URL state tracking, SQLite FTS5 indexing, weighted BM25 ranking, search API, and connected React results page.

## Project structure

- frontend/ — React + Vite search experience
- backend/ — FastAPI API, Apokolips Spider, SQLite store, and FTS5 search index
- crawler/ — crawler behaviour and operating documentation
- indexer/ — future standalone/background indexing pipeline
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

- POST /crawl — crawl a small permitted seed set and persist extracted pages.
- GET /search?q=... — search the local Apokolips index with BM25 ranking.
- GET /stats — database and index statistics.
- GET /crawl/runs — recent crawl history.
- GET /crawl/runs/{run_id} — one crawl run's status and metrics.
- GET /health — API, database, and FTS5 health check.

The SQLite database is created at backend/data/apokolips-search.sqlite3. Set APOKOLIPS_DB_PATH to choose another location. The database is local application data and is excluded from Git.

## Search design

The current local implementation uses SQLite FTS5 with Unicode tokenization and weighted BM25 field ranking: title 20, description 3, headings 5, and body 1. Search terms use AND semantics and results are paginated. Image, video, and news search verticals are not implemented yet.

## Validation

GitHub Actions checks Python 3.11 and 3.12 (Ruff plus backend tests) and builds the frontend with Node.js 22. Tests use temporary databases and mocked crawler output; they do not crawl live sites.

## Responsible crawling

Respect robots.txt, applicable site terms, access restrictions, and publisher preferences. Use the crawler only on sites you are authorized to crawl. It does not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. See crawler/README.md for its limits.
