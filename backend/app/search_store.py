"""Durable SQLite metadata store and first-party FTS5 search index."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from .crawler.parsing import ExtractedDocument
from .crawler.spider import CrawlIssue, CrawlReport


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_fts_query(query: str) -> str:
    """Build a safe FTS5 AND query from plain user-entered words."""
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Search query must be 1–200 characters")
    tokens = re.findall(r"[^\W_]+", query, flags=re.UNICODE)
    tokens = [token for token in tokens if token.strip()]
    if not tokens:
        raise ValueError("Search query must contain at least one searchable word")
    if len(tokens) > 12:
        raise ValueError("Search query may contain at most 12 searchable words")
    # Every token is double-quoted, so words such as AND, OR, and NEAR
    # are treated as search terms, never as raw FTS5 syntax.
    return " AND ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)


class SearchStore:
    """Owns crawl metadata, extracted documents, and the local FTS5 index."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        if database_path is None:
            configured_path = os.getenv("APOKOLIPS_DB_PATH")
            database_path = (
                Path(configured_path)
                if configured_path
                else Path(__file__).resolve().parents[1] / "data" / "apokolips-search.sqlite3"
            )
        self.database_path = Path(database_path).expanduser().resolve()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        """Create or safely upgrade the local metadata and full-text schema."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS crawl_runs (
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
                    seeds_json TEXT NOT NULL,
                    processed_urls INTEGER NOT NULL DEFAULT 0,
                    discovered_urls INTEGER NOT NULL DEFAULT 0,
                    indexed_pages INTEGER NOT NULL DEFAULT 0,
                    issue_count INTEGER NOT NULL DEFAULT 0,
                    elapsed_seconds REAL,
                    error_message TEXT
                );

                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY,
                    url TEXT NOT NULL,
                    canonical_url TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    language TEXT NOT NULL DEFAULT '',
                    headings_json TEXT NOT NULL DEFAULT '[]',
                    body TEXT NOT NULL DEFAULT '',
                    content_hash TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_crawled_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS crawl_url_state (
                    url TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK (status IN ('indexed', 'issue')),
                    last_run_id TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
                    last_crawled_at TEXT NOT NULL,
                    last_error_code TEXT,
                    last_error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_documents_last_crawled
                    ON documents(last_crawled_at DESC);
                CREATE INDEX IF NOT EXISTS idx_crawl_runs_started
                    ON crawl_runs(started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_crawl_url_state_status
                    ON crawl_url_state(status);
                """
            )
            fts_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(documents_fts)").fetchall()
            }
            rebuild_fts = not fts_columns
            if fts_columns and "headings_json" not in fts_columns:
                # Early development snapshots used a mismatched external-content
                # column name. Recreate the FTS virtual table and rebuild it safely.
                connection.executescript(
                    """
                    DROP TRIGGER IF EXISTS documents_ai;
                    DROP TRIGGER IF EXISTS documents_ad;
                    DROP TRIGGER IF EXISTS documents_au;
                    DROP TABLE IF EXISTS documents_fts;
                    """
                )
                rebuild_fts = True

            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
                    USING fts5(
                        title,
                        description,
                        headings_json,
                        body,
                        content='documents',
                        content_rowid='id',
                        tokenize='unicode61 remove_diacritics 2'
                    )
                    """
                )
            except sqlite3.OperationalError as exc:
                raise RuntimeError(
                    "This Python SQLite build does not include FTS5. "
                    "Install a Python build with SQLite FTS5 support."
                ) from exc

            connection.executescript(
                """
                CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                    INSERT INTO documents_fts(rowid, title, description, headings_json, body)
                    VALUES (new.id, new.title, new.description, new.headings_json, new.body);
                END;

                CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                    INSERT INTO documents_fts(
                        documents_fts, rowid, title, description, headings_json, body
                    )
                    VALUES (
                        'delete', old.id, old.title, old.description,
                        old.headings_json, old.body
                    );
                END;

                CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                    INSERT INTO documents_fts(
                        documents_fts, rowid, title, description, headings_json, body
                    )
                    VALUES (
                        'delete', old.id, old.title, old.description,
                        old.headings_json, old.body
                    );
                    INSERT INTO documents_fts(rowid, title, description, headings_json, body)
                    VALUES (new.id, new.title, new.description, new.headings_json, new.body);
                END;
                """
            )
            if rebuild_fts:
                connection.execute(
                    "INSERT INTO documents_fts(documents_fts) VALUES ('rebuild')"
                )

    def create_crawl_run(self, seeds: list[str]) -> str:
        """Persist a crawl run as soon as it is accepted by the API."""
        run_id = uuid.uuid4().hex
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_runs (id, started_at, status, seeds_json)
                VALUES (?, ?, 'running', ?)
                """,
                (run_id, now, json.dumps(seeds, ensure_ascii=False)),
            )
        return run_id

    @staticmethod
    def _upsert_one(connection: sqlite3.Connection, page: ExtractedDocument, now: str) -> int:
        existing = connection.execute(
            "SELECT id FROM documents WHERE canonical_url = ?",
            (page.canonical_url,),
        ).fetchone()
        if existing is None:
            cursor = connection.execute(
                """
                INSERT INTO documents (
                    url, canonical_url, title, description, language, headings_json,
                    body, content_hash, first_seen_at, last_crawled_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    page.url,
                    page.canonical_url,
                    page.title,
                    page.description,
                    page.language,
                    json.dumps(list(page.headings), ensure_ascii=False),
                    page.text,
                    page.content_hash,
                    now,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid)

        document_id = int(existing["id"])
        connection.execute(
            """
            UPDATE documents
            SET url = ?, title = ?, description = ?, language = ?,
                headings_json = ?, body = ?, content_hash = ?,
                last_crawled_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                page.url,
                page.title,
                page.description,
                page.language,
                json.dumps(list(page.headings), ensure_ascii=False),
                page.text,
                page.content_hash,
                now,
                now,
                document_id,
            ),
        )
        return document_id

    def upsert_documents(self, pages: Iterable[ExtractedDocument]) -> int:
        """Insert or refresh documents and update their FTS entries atomically."""
        now = utc_now()
        count = 0
        with self._connect() as connection:
            for page in pages:
                self._upsert_one(connection, page, now)
                count += 1
        return count

    def save_crawl_result(self, run_id: str, report: CrawlReport) -> int:
        """Persist extracted pages, per-URL crawl state, and final run metrics."""
        now = utc_now()
        indexed_count = 0
        with self._connect() as connection:
            run = connection.execute(
                "SELECT id FROM crawl_runs WHERE id = ?",
                (run_id,),
            ).fetchone()
            if run is None:
                raise ValueError("Crawl run does not exist")

            for page in report.pages:
                self._upsert_one(connection, page, now)
                connection.execute(
                    """
                    INSERT INTO crawl_url_state (
                        url, status, last_run_id, last_crawled_at,
                        last_error_code, last_error_message
                    )
                    VALUES (?, 'indexed', ?, ?, NULL, NULL)
                    ON CONFLICT(url) DO UPDATE SET
                        status = 'indexed',
                        last_run_id = excluded.last_run_id,
                        last_crawled_at = excluded.last_crawled_at,
                        last_error_code = NULL,
                        last_error_message = NULL
                    """,
                    (page.url, run_id, now),
                )
                indexed_count += 1

            for issue in report.issues:
                connection.execute(
                    """
                    INSERT INTO crawl_url_state (
                        url, status, last_run_id, last_crawled_at,
                        last_error_code, last_error_message
                    )
                    VALUES (?, 'issue', ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        status = 'issue',
                        last_run_id = excluded.last_run_id,
                        last_crawled_at = excluded.last_crawled_at,
                        last_error_code = excluded.last_error_code,
                        last_error_message = excluded.last_error_message
                    """,
                    (issue.url, run_id, now, issue.code, issue.message[:500]),
                )

            connection.execute(
                """
                UPDATE crawl_runs
                SET finished_at = ?, status = 'completed',
                    processed_urls = ?, discovered_urls = ?,
                    indexed_pages = ?, issue_count = ?, elapsed_seconds = ?
                WHERE id = ?
                """,
                (
                    now,
                    report.processed_urls,
                    report.discovered_urls,
                    indexed_count,
                    len(report.issues),
                    report.elapsed_seconds,
                    run_id,
                ),
            )
        return indexed_count

    def fail_crawl_run(self, run_id: str, message: str) -> None:
        now = utc_now()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE crawl_runs
                SET finished_at = ?, status = 'failed', error_message = ?
                WHERE id = ? AND status = 'running'
                """,
                (now, message[:500], run_id),
            )

    def search(self, query: str, page: int = 1, page_size: int = 10) -> dict:
        """Search only Apokolips' own FTS5 index, ranked with weighted BM25."""
        if not 1 <= page <= 10_000:
            raise ValueError("page must be between 1 and 10000")
        if not 1 <= page_size <= 50:
            raise ValueError("page_size must be between 1 and 50")
        match_query = build_fts_query(query)
        offset = (page - 1) * page_size

        with self._connect() as connection:
            total = int(
                connection.execute(
                    """
                    SELECT COUNT(*)
                    FROM documents_fts
                    WHERE documents_fts MATCH ?
                    """,
                    (match_query,),
                ).fetchone()[0]
            )
            rows = connection.execute(
                """
                SELECT
                    d.id,
                    d.url,
                    d.canonical_url,
                    d.title,
                    d.description,
                    d.language,
                    snippet(documents_fts, 3, '', '', ' … ', 28) AS excerpt,
                    bm25(documents_fts, 20.0, 3.0, 5.0, 1.0) AS bm25_rank,
                    d.last_crawled_at
                FROM documents_fts
                JOIN documents AS d ON d.id = documents_fts.rowid
                WHERE documents_fts MATCH ?
                ORDER BY bm25_rank ASC, d.last_crawled_at DESC
                LIMIT ? OFFSET ?
                """,
                (match_query, page_size, offset),
            ).fetchall()

        results = []
        for row in rows:
            excerpt = (row["excerpt"] or "").strip()
            if not excerpt:
                excerpt = (row["description"] or "").strip()
            results.append(
                {
                    "id": int(row["id"]),
                    "url": row["url"],
                    "canonical_url": row["canonical_url"],
                    "title": row["title"] or row["canonical_url"],
                    "description": row["description"],
                    "language": row["language"],
                    "snippet": excerpt[:500],
                    "relevance_score": round(max(0.0, -float(row["bm25_rank"])), 8),
                    "last_crawled_at": row["last_crawled_at"],
                }
            )

        total_pages = (total + page_size - 1) // page_size
        return {
            "query": query,
            "total_results": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "has_more": page < total_pages,
            "results": results,
        }

    def get_stats(self) -> dict[str, int | str]:
        with self._connect() as connection:
            document_count = int(
                connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            )
            run_count = int(
                connection.execute("SELECT COUNT(*) FROM crawl_runs").fetchone()[0]
            )
            completed_runs = int(
                connection.execute(
                    "SELECT COUNT(*) FROM crawl_runs WHERE status = 'completed'"
                ).fetchone()[0]
            )
            queued_or_running = int(
                connection.execute(
                    "SELECT COUNT(*) FROM crawl_runs WHERE status = 'running'"
                ).fetchone()[0]
            )
            url_count = int(
                connection.execute("SELECT COUNT(*) FROM crawl_url_state").fetchone()[0]
            )
        return {
            "documents_indexed": document_count,
            "tracked_urls": url_count,
            "crawl_runs": run_count,
            "completed_crawl_runs": completed_runs,
            "running_crawl_runs": queued_or_running,
            "index": "SQLite FTS5",
        }

    def list_crawl_runs(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, started_at, finished_at, status, seeds_json,
                       processed_urls, discovered_urls, indexed_pages,
                       issue_count, elapsed_seconds, error_message
                FROM crawl_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                **dict(row),
                "seeds": json.loads(row["seeds_json"]),
            }
            for row in rows
        ]

    def get_crawl_run(self, run_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, started_at, finished_at, status, seeds_json,
                       processed_urls, discovered_urls, indexed_pages,
                       issue_count, elapsed_seconds, error_message
                FROM crawl_runs
                WHERE id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["seeds"] = json.loads(result.pop("seeds_json"))
        return result

    def health(self) -> bool:
        with self._connect() as connection:
            connection.execute("SELECT 1")
            connection.execute("SELECT COUNT(*) FROM documents_fts").fetchone()
        return True
