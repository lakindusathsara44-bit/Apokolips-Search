# Apokolips Search — Architecture

## Goals

Build an independent search engine with its own crawler, document pipeline, index, ranking, and user-facing search API. The project must not present third-party search results as its own index.

## Logical flow

1. Discovery / crawler finds public URLs through seed lists, links, and XML sitemaps.
2. Fetch and parse retrieves permitted pages with bounded resources and extracts text and metadata.
3. Indexer normalizes URLs, deduplicates documents, and writes searchable fields to OpenSearch.
4. Metadata database stores crawl state, source information, timestamps, and operational records in PostgreSQL.
5. Search API validates queries, retrieves candidates, applies ranking and filters, and returns paginated results.
6. Frontend renders search results and category-specific experiences.

## Planned components

- React + Vite frontend
- Python + FastAPI API
- Python crawler workers
- PostgreSQL metadata store
- OpenSearch full-text index
- Redis-backed job queue when background workers are introduced

## Local-first deployment

Phase 01 runs the frontend and API locally. Database, OpenSearch, and queue services will be introduced through optional local containers in later phases after resource requirements are measured.

## Responsible crawling and privacy

Respect robots.txt, applicable terms and access controls, per-host rate limits, and publisher crawl preferences. Identify the crawler clearly. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. Reject loopback, private, link-local, and other non-public IP destinations to mitigate SSRF. Limit response sizes and content types. Retain only data needed for search and operations. Avoid collecting sensitive personal data. Provide a removal/contact process and honour valid publisher requests.

## Ranking principles

Start with BM25 and weighted title, heading, and body fields. Add quality, freshness, language, spam, and link-derived signals only with measurable evaluation and abuse resistance. Do not sell ranking placement without clear labelling.