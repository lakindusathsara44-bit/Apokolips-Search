# Apokolips Search — Architecture

## Goals

Build an independent search engine with its own crawler, index, ranking, and user-facing search API. Search results must come from Apokolips' own index, not be presented from a third-party search API.

## Logical flow

1. Discovery: Apokolips Spider discovers public URLs from seed lists, robots.txt sitemap directives, XML sitemaps, and page links.
2. Policy and fetch: the crawler checks robots.txt, applies per-host rate limits, restricts outbound destinations to globally routable addresses, and applies request/response limits.
3. Extraction: HTML title, description, canonical URL, language, headings, body text, and links are extracted.
4. Persistence: crawl runs, per-URL states, and normalized documents are stored in a local SQLite database.
5. Indexing: SQLite FTS5 maintains a full-text index with Unicode tokenization.
6. Search: the FastAPI endpoint sanitizes user input and ranks local-index matches with weighted BM25.
7. Frontend: the React search page calls the local API, displays ranked results, and supports pagination.

## Phase status

- Phase 01: React + Vite + TypeScript frontend and FastAPI foundation — merged.
- Phase 02: bounded Apokolips Spider crawler, robots.txt and sitemap handling, HTML extraction, safe URL validation, per-host throttling, response limits, and tests — implemented in \`feature/phase-02-safe-crawler\`.
- Phase 03: durable SQLite crawl metadata, URL state tracking, FTS5 indexing, weighted BM25 search API, frontend integration, and database/API tests — implemented in \`feature/phase-03-database-search\`.

## Local-first data architecture

SQLite is deliberately used for the first local implementation. It keeps the installation lightweight and avoids requiring PostgreSQL, Redis, Java, or a separate OpenSearch service on the development laptop. The FTS5 engine is built into supported SQLite builds and provides full-text matching and BM25 ranking.

The database is stored at \`backend/data/apokolips-search.sqlite3\` by default. Set \`APOKOLIPS_DB_PATH\` to use another local path. SQLite WAL mode and a busy timeout support reliable local reads and writes. The database is excluded from Git.

The search index is rebuilt/maintained by SQLite triggers when document rows are inserted, updated, or deleted. Ranking weights favour titles, then headings, descriptions, and body text. The first release uses AND semantics across query terms for predictable matching.

## Current limitations

- Crawl execution is request-driven and bounded; there is not yet a continuously running scheduler or background worker queue.
- The local search index contains only pages that have actually been crawled and stored. It is not a copy of the entire web.
- Web search is connected to the local index. Image, video, and news verticals are planned separately.
- Advanced ranking signals, language-specific analysis, link graph scoring, and spam-quality systems need evaluation datasets before adoption.
- SQLite is a practical local foundation. A multi-user production service can later migrate persistence and indexing to PostgreSQL/OpenSearch without changing the product goal.

## Responsible crawling and privacy

Respect robots.txt, applicable terms and access controls, per-host rate limits, and publisher crawl preferences. Identify the crawler clearly. Do not bypass authentication, paywalls, CAPTCHAs, or technical restrictions. Reject loopback, private, link-local, and other non-public IP destinations at DNS resolution time, including mixed public/private DNS answers. Revalidate redirect destinations. Limit response sizes and content types. Retain only data needed for search and operations. Avoid collecting sensitive personal data. Provide a removal/contact process and honour valid publisher requests.

## Ranking principles

Use BM25 with title, heading, description, and body field weighting. Add quality, freshness, language, spam, and link-derived signals only with measurable evaluation and abuse resistance. Do not sell ranking placement without clear labelling.
