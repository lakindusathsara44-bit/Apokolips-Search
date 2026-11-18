# Apokolips Search — Architecture

## Goals

Build an independent search engine with its own crawler, index, ranking, and user-facing search API. Search results must come from Apokolips' own index, not be presented from a third-party search API.

## Logical flow

1. Discovery / crawler finds public URLs through seed lists, links, and XML sitemaps.
2. Fetch and parse retrieves permitted pages with bounded resources and extracts text and metadata.
3. Indexer normalizes URLs, deduplicates documents, and writes searchable fields to OpenSearch.
4. Metadata database stores crawl state, source information, timestamps, and operational records in PostgreSQL.
5. Search API validates queries, retrieves candidates, applies ranking and filters, and returns paginated results.
6. Frontend renders search results and category-specific experiences.

## Phase status

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation — merged.
- Phase 02: bounded Apokolips Spider crawler, robots.txt and sitemap handling, HTML extraction, safe URL validation, per-host throttling, response limits, and unit tests — implemented in the crawler feature branch.
- Phase 03: durable crawl-state storage, scheduling/queue, PostgreSQL metadata, OpenSearch index, and first-party search endpoint — not implemented.

## Planned components

- React + Vite frontend
- Python + FastAPI API
- Python crawler workers
- PostgreSQL metadata store
- OpenSearch full-text index
- Redis-backed job queue when background workers are introduced

## Local-first deployment

The first two phases run locally. Database, OpenSearch, and queue services will be introduced through optional local containers in later phases after resource requirements are measured.

## Responsible crawling and privacy

Respect robots.txt, applicable terms and access controls, per-host rate limits, and publisher crawl preferences. Identify the crawler clearly. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. Reject loopback, private, link-local, and other non-public IP destinations at DNS resolution time, including mixed public/private DNS answers. Revalidate redirect destinations. Limit response sizes and content types. Retain only data needed for search and operations. Avoid collecting sensitive personal data. Provide a removal/contact process and honour valid publisher requests.

## Ranking principles

Start with BM25 and weighted title, heading, and body fields. Add quality, freshness, language, spam, and link-derived signals only with measurable evaluation and abuse resistance.
