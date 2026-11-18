# Apokolips Search — Architecture

## Goals

Build an independent search engine with its own crawler, index, ranking, and public developer API. Search results come from Apokolips' own index, not from a third-party search API.

## Logical flow

1. Discovery: Apokolips Spider discovers public URLs from seed lists, robots.txt sitemap directives, XML sitemaps, and page links.
2. Policy and fetch: the crawler checks robots.txt, applies per-host rate limits, restricts outbound destinations to globally routable addresses, and applies request/response limits.
3. Extraction: HTML title, description, canonical URL, language, headings, body text, and links are extracted.
4. Persistence: crawl runs, per-URL states, normalized documents, API-key hashes, and usage buckets are stored in SQLite.
5. Queueing: crawl requests are persisted as jobs and atomically claimed by a background worker using SQLite transactions and short-lived leases.
6. Indexing: SQLite FTS5 maintains a full-text index.
7. Search: FastAPI sanitizes query input and ranks local-index matches with weighted BM25.
8. Public access: `GET /api/v1/search` authenticates a high-entropy API key, atomically consumes its per-minute quota, and returns paginated JSON.
9. Administration: a separate administrator bearer token controls key creation/revocation and protects crawler/operational endpoints in public mode.
10. Frontend: the React search page calls the local search API, displays ranked results, and supports pagination.

## Phase status

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation.
- Phase 02: bounded Apokolips Spider crawler, robots.txt and sitemap handling, HTML extraction, safe URL validation, per-host throttling, response limits, and tests.
- Phase 03: durable SQLite crawl metadata, URL state tracking, FTS5 indexing, weighted BM25 search API, frontend integration, and database/API tests.
- Phase 04: durable SQLite crawl jobs, one background worker per API process, atomic claims, 180-second leases, restart recovery, bounded retries, status queries, and pending-job cancellation.
- Phase 05: public Search API v1, hashed API keys, per-key fixed UTC-minute quotas, admin-only key management, public-mode crawler protections, and developer documentation.

## Local-first data architecture

SQLite keeps installation lightweight and avoids requiring PostgreSQL, Redis, Java, or a separate OpenSearch service for local development. FTS5 provides full-text matching and BM25 ranking. The default database is `backend/data/apokolips-search.sqlite3`; set `APOKOLIPS_DB_PATH` to another path. SQLite WAL mode and a busy timeout support local reads and writes. The database is excluded from Git.

The search index is maintained by SQLite triggers when document rows are inserted, updated, or deleted. Ranking weights favour titles, then headings, descriptions, and body text. The first release uses AND semantics across query terms.

## Queue reliability model

The `crawl_jobs` table shares the search database. Workers claim one pending job inside a `BEGIN IMMEDIATE` transaction. Each claim has a 180-second lease. Interrupted jobs are recovered after restart while attempts remain; otherwise they become terminal failures. The default maximum is three attempts with short exponential backoff. A pending job can be cancelled.

The worker uses the bounded crawler configuration: at most 25 pages per job, depth at most 3, and a 120-second crawl timeout. Crawler policy and network-safety checks are shared; the queue does not bypass robots.txt or other protections.

## Public API security model

The public API exposes search only. Each developer key is generated from cryptographically secure randomness, prefixed `aps_live_`, and returned once. SQLite stores only its SHA-256 hash and non-secret metadata. Keys have independent per-minute quotas (default 60; configurable from 1 to 600). Quota increments occur inside a SQLite write transaction to prevent concurrent requests from exceeding the same window. Revocation takes effect on the next request.

Administrator operations use `Authorization: Bearer` and the `APOKOLIPS_ADMIN_TOKEN` environment variable. Public mode requires a token of at least 32 characters. In public mode the old unmetered `/search` endpoint is disabled and crawler submissions, job inspection/cancellation, crawl history, and statistics are administrator-only. API key management is administrator-only in every mode.

CORS allows only explicit origins configured in `APOKOLIPS_CORS_ORIGINS`; wildcard origins are ignored. CORS is not an authentication mechanism. Public API keys must not be embedded in client-side JavaScript or committed to source control. Public deployments must terminate HTTPS and keep the admin token in a secret manager.

## Deployment boundary and limitations

This implementation adds the public API contract and access controls; it does not by itself host a live public service. The current database, worker, and fixed-window quota storage are designed for a single API instance with one persistent SQLite database. Do not horizontally scale independent instances or use ephemeral storage. A production multi-instance service will require shared transactional storage, coordinated worker infrastructure, stronger operational monitoring, and abuse controls.

The index contains only pages actually crawled and stored. It is not a copy of the entire web. Image, video, and news verticals are planned separately. Advanced ranking signals need evaluation datasets before adoption.

## Responsible crawling and privacy

Respect robots.txt, applicable terms and access controls, per-host rate limits, and publisher preferences. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. Reject private and non-public network destinations, revalidate redirects, and limit response sizes/content types. Retain only data needed for search and operations. Avoid collecting sensitive personal data and provide a removal/contact process.

## Ranking principles

Use BM25 with title, heading, description, and body field weighting. Add quality, freshness, language, spam, and link-derived signals only with measurable evaluation and abuse resistance. Do not sell ranking placement without clear labelling.
