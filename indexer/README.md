# Indexer

The first local search index is implemented in backend/app/search_store.py using SQLite FTS5.

## Current implementation

- Canonical-URL document upsert and content refresh.
- SQLite external-content full-text index with insert/update/delete triggers.
- Unicode tokenization with diacritic removal.
- Weighted BM25 relevance ranking: title 20, description 3, headings 5, body 1.
- Safe search-term construction, AND semantics, result excerpts, and pagination.
- FTS schema migration and index rebuild support.

The FTS5 index is maintained automatically when the crawler persists documents. It does not require a separate indexing service or OpenSearch installation for local development.

## Future work

This directory is reserved for a future standalone/background indexing worker and production-scale search infrastructure. Any future PostgreSQL/OpenSearch migration must preserve the rule that search results are derived from Apokolips-crawled and indexed content, not copied from a third-party search API.
