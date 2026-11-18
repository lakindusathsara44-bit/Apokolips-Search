# Apokolips Search

An independent web search engine project by Apokolips.

## Project status

Phase 01 — Foundation.

## Architecture

- `frontend/` — React + Vite search interface
- `backend/` — FastAPI application and health endpoint
- `crawler/` — future web discovery and crawling workers
- `indexer/` — future document processing and indexing
- `admin/` — future administration interface
- `infrastructure/` — local development infrastructure
- `docs/` — architecture and implementation documentation

## Development

The initial foundation is designed for local development. Search results will come only from Apokolips' own crawler and index; no third-party search engine API is used as the primary search provider.

See `docs/architecture.md` and `docs/local-development.md` for the planned system and setup.