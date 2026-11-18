"""Durable SQLite-backed crawl job queue with leases and bounded retries."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


class CrawlQueue:
    """A small durable queue sharing the search application's SQLite database."""

    def __init__(self, database_path: str | Path) -> None:
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
        """Create the queue schema and recover jobs left by a stopped worker."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        now = _timestamp(utc_now())
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS crawl_jobs (
                    id TEXT PRIMARY KEY,
                    seeds_json TEXT NOT NULL,
                    max_pages INTEGER NOT NULL CHECK (max_pages BETWEEN 1 AND 25),
                    max_depth INTEGER NOT NULL CHECK (max_depth BETWEEN 0 AND 3),
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'running', 'completed', 'failed', 'cancelled')
                    ),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    available_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 5),
                    worker_id TEXT,
                    lease_expires_at TEXT,
                    run_id TEXT REFERENCES crawl_runs(id) ON DELETE SET NULL,
                    error_message TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_crawl_jobs_pending
                    ON crawl_jobs(status, available_at, created_at);
                CREATE INDEX IF NOT EXISTS idx_crawl_jobs_lease
                    ON crawl_jobs(status, lease_expires_at);
                """
            )

            # The previous process cannot resume an interrupted HTTP crawl.
            # Retry it once the new worker starts, with an explicit audit message.
            connection.execute(
                """
                UPDATE crawl_jobs
                SET status = CASE
                        WHEN attempts < max_attempts THEN 'pending'
                        ELSE 'failed'
                    END,
                    updated_at = ?,
                    available_at = ?,
                    finished_at = CASE
                        WHEN attempts < max_attempts THEN NULL
                        ELSE ?
                    END,
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    error_message = 'Worker restarted before the job completed'
                WHERE status = 'running'
                """,
                (now, now, now),
            )

    @staticmethod
    def _serialize(row: sqlite3.Row | None) -> dict | None:
        if row is None:
            return None
        item = dict(row)
        item["seeds"] = json.loads(item.pop("seeds_json"))
        return item

    def enqueue(
        self,
        seeds: list[str],
        max_pages: int = 5,
        max_depth: int = 1,
        max_attempts: int = 3,
    ) -> dict:
        """Persist a bounded crawl request without starting network activity."""
        if not 1 <= len(seeds) <= 10:
            raise ValueError("A crawl job must contain between 1 and 10 seed URLs")
        if not 1 <= max_pages <= 25 or not 0 <= max_depth <= 3:
            raise ValueError("Crawl limits are outside the supported bounds")
        if not 1 <= max_attempts <= 5:
            raise ValueError("max_attempts must be between 1 and 5")

        job_id = uuid.uuid4().hex
        now = _timestamp(utc_now())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO crawl_jobs (
                    id, seeds_json, max_pages, max_depth, status,
                    created_at, updated_at, available_at, max_attempts
                )
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
                """,
                (
                    job_id,
                    json.dumps(seeds, ensure_ascii=False),
                    max_pages,
                    max_depth,
                    now,
                    now,
                    now,
                    max_attempts,
                ),
            )
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        result = self._serialize(row)
        assert result is not None
        return result

    def get_job(self, job_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._serialize(row)

    def list_jobs(self, limit: int = 20) -> list[dict]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM crawl_jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._serialize(row) for row in rows if row is not None]

    def claim_next_job(self, worker_id: str, lease_seconds: int = 180) -> dict | None:
        """Atomically claim one ready job; concurrent workers cannot double-claim."""
        now_dt = utc_now()
        now = _timestamp(now_dt)
        lease_until = _timestamp(now_dt + timedelta(seconds=lease_seconds))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE crawl_jobs
                SET status = CASE
                        WHEN attempts < max_attempts THEN 'pending'
                        ELSE 'failed'
                    END,
                    updated_at = ?,
                    available_at = ?,
                    finished_at = CASE
                        WHEN attempts < max_attempts THEN NULL
                        ELSE ?
                    END,
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    error_message = 'Worker lease expired; job will be retried'
                WHERE status = 'running'
                  AND lease_expires_at IS NOT NULL
                  AND lease_expires_at <= ?
                """,
                (now, now, now, now),
            )
            row = connection.execute(
                """
                SELECT * FROM crawl_jobs
                WHERE status = 'pending' AND available_at <= ?
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if row is None:
                return None

            connection.execute(
                """
                UPDATE crawl_jobs
                SET status = 'running',
                    attempts = attempts + 1,
                    worker_id = ?,
                    started_at = COALESCE(started_at, ?),
                    updated_at = ?,
                    lease_expires_at = ?,
                    finished_at = NULL,
                    run_id = NULL,
                    error_message = NULL
                WHERE id = ? AND status = 'pending'
                """,
                (worker_id, now, now, lease_until, row["id"]),
            )
            claimed = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (row["id"],),
            ).fetchone()
        return self._serialize(claimed)

    def attach_run(self, job_id: str, worker_id: str, run_id: str) -> bool:
        now = _timestamp(utc_now())
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE crawl_jobs
                SET run_id = ?, updated_at = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (run_id, now, job_id, worker_id),
            )
        return cursor.rowcount == 1

    def complete(self, job_id: str, worker_id: str) -> bool:
        now = _timestamp(utc_now())
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE crawl_jobs
                SET status = 'completed', updated_at = ?, finished_at = ?,
                    worker_id = NULL, lease_expires_at = NULL, error_message = NULL
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (now, now, job_id, worker_id),
            )
        return cursor.rowcount == 1

    def fail(
        self,
        job_id: str,
        worker_id: str,
        message: str,
        retry_delay_seconds: int = 0,
    ) -> dict | None:
        """Return a failed attempt to the queue or mark it terminal after retries."""
        now_dt = utc_now()
        now = _timestamp(now_dt)
        available_at = _timestamp(now_dt + timedelta(seconds=max(0, retry_delay_seconds)))
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE crawl_jobs
                SET status = CASE
                        WHEN attempts < max_attempts THEN 'pending'
                        ELSE 'failed'
                    END,
                    updated_at = ?,
                    available_at = ?,
                    finished_at = CASE
                        WHEN attempts < max_attempts THEN NULL
                        ELSE ?
                    END,
                    worker_id = NULL,
                    lease_expires_at = NULL,
                    error_message = ?
                WHERE id = ? AND status = 'running' AND worker_id = ?
                """,
                (now, available_at, now, message[:500], job_id, worker_id),
            )
            row = connection.execute(
                "SELECT * FROM crawl_jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        return self._serialize(row)

    def cancel_pending(self, job_id: str) -> bool:
        now = _timestamp(utc_now())
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE crawl_jobs
                SET status = 'cancelled', updated_at = ?, finished_at = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, now, job_id),
            )
        return cursor.rowcount == 1
