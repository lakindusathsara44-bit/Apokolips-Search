# Apokolips Search — Architecture

## Goals

Build an independent search engine with its own crawler, index, ranking, and user-facing search API. Search results must come from Apokolips' own index, not be presented from a third-party search API.

## Logical flow

1. Discovery: Apokolips Spider discovers public URLs from seed lists, robots.txt sitemap directives, XML sitemaps, and page links.
2. Policy and fetch: the crawler checks robots.txt, applies per-host rate limits, restricts outbound destinations to globally routable addresses, and applies request/response limits.
3. Extraction: HTML title, description, canonical URL, language, headings, body text, and links are extracted.
4. Persistence: crawl runs, per-URL states, and normalized documents are stored in a local SQLite database.
5. Queueing: crawl requests are persisted as jobs and atomically claimed by a background worker using SQLite transactions and short-lived leases.
6. Indexing: SQLite FTS5 maintains a full-text index.
7. Search: the FastAPI endpoint sanitizes user input and ranks local-index matches with weighted BM25.
8. Frontend: the React search page calls the local API, displays ranked results, and supports pagination.

## Phase status

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation.
- Phase 02: bounded Apokolips Spider crawler, robots.txt and sitemap handling, HTML extraction, safe URL validation, per-host throttling, response limits, and tests.
- Phase 03: durable SQLite crawl metadata, URL state tracking, FTS5 indexing, weighted BM25 search API, frontend integration, and database/API tests.
- Phase 04: durable SQLite crawl jobs, one background worker per API process, atomic claims, 180-second leases, restart recovery, bounded retries, status queries, and pending-job cancellation.

## Local-first data architecture

SQLite is deliberately used for the first local implementation. It keeps the installation lightweight and avoids requiring PostgreSQL, Redis, Java, or a separate OpenSearch service on the development laptop. The FTS5 engine is built into supported SQLite builds and provides full-text matching and BM25 ranking.

The database is stored at `backend/data/apokolips-search.sqlite3` by default. Set `APOKOLIPS_DB_PATH` to use another local path. SQLite WAL mode and a busy timeout support reliable local reads and writes. The database is excluded from Git.

The search index is maintained by SQLite triggers when document rows are inserted, updated, or deleted. Ranking weights favour titles, then headings, descriptions, and body text. The first release uses AND semantics across query terms for predictable matching.

## Queue reliability model

The `crawl_jobs` table is stored in the same database as the search index. Workers claim one pending job inside a `BEGIN IMMEDIATE` transaction so two local worker loops cannot claim the same pending row. Each claim has a 180-second lease. If a worker disappears or the application restarts, expired/in-flight jobs are returned to the pending queue while attempts remain, otherwise they become terminal failures. The default maximum is three attempts with short exponential backoff. A pending job can be cancelled; in-progress cancellation is intentionally not advertised.

The worker applies the same bounded crawler configuration as the synchronous endpoint: at most 25 pages per job, depth at most 3, and a 120-second crawl timeout. Crawler policy and network-safety checks are shared; the queue does not bypass robots.txt or other crawler protections.

This is a local single-process service with SQLite persistence, not a distributed queue, public multi-tenant service, or recurring cron scheduler. The API should remain bound to localhost until authentication, quotas, and abuse controls are added.

## Current limitations

- The worker processes one job at a time per API process; no multi-worker deployment or external broker is configured.
- Jobs are request-driven; recurring scheduled crawls are not implemented.
- The local search index contains only pages that have actually been crawled and stored. It is not a copy of the entire web.
- Web search is connected to the local index. Image, video, and news verticals are planned separately.
- Advanced ranking signals, language-specific analysis, link graph scoring, and spam-quality systems need evaluation datasets before adoption.
- SQLite is a practical local foundation. A multi-user production service can later migrate persistence and indexing to PostgreSQL/OpenSearch without changing the product goal.

## Responsible crawling and privacy

Respect robots.txt, applicable terms and access controls, per-host rate limits, and publisher crawl preferences. Identify the crawler clearly. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. Reject loopback, private, link-local, and other non-public IP destinations at DNS resolution time, including mixed public/private DNS answers. Revalidate redirect destinations. Limit response sizes and content types. Retain only data needed for search and operations. Avoid collecting sensitive personal data. Provide a removal/contact process and honour valid publisher requests.

## Ranking principles

Use BM25 with title, heading, description, and body field weighting. Add quality, freshness, language, spam, and link-derived signals only with measurable evaluation and abuse resistance. Do not sell ranking placement without clear labelling.
