"""API-key management and per-key rate limiting for the public search API."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def _utc_now() -> datetime:
    return datetime.now(UTC)


class APIKeyStore:
    """Store only API-key hashes and enforce fixed-window request quotas."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    key_prefix TEXT NOT NULL,
                    key_hash TEXT NOT NULL UNIQUE,
                    requests_per_minute INTEGER NOT NULL
                        CHECK (requests_per_minute BETWEEN 1 AND 600),
                    created_at TEXT NOT NULL,
                    last_used_at TEXT,
                    revoked_at TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS api_key_usage (
                    api_key_id TEXT NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
                    window_start TEXT NOT NULL,
                    request_count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (api_key_id, window_start)
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_api_keys_created ON api_keys(created_at DESC)"
            )

    @staticmethod
    def _hash(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def create_key(self, name: str, requests_per_minute: int = 60) -> dict:
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Key name must contain 1–80 characters")
        if not 1 <= requests_per_minute <= 600:
            raise ValueError("requests_per_minute must be between 1 and 600")

        raw_key = "aps_live_" + secrets.token_urlsafe(32)
        key_id = uuid.uuid4().hex
        prefix = raw_key[:16]
        now = _utc_now().isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO api_keys (
                    id, name, key_prefix, key_hash, requests_per_minute, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    key_id,
                    clean_name,
                    prefix,
                    self._hash(raw_key),
                    requests_per_minute,
                    now,
                ),
            )
        return {
            "id": key_id,
            "name": clean_name,
            "key_prefix": prefix,
            "api_key": raw_key,
            "requests_per_minute": requests_per_minute,
            "created_at": now,
        }

    def list_keys(self) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, key_prefix, requests_per_minute,
                       created_at, last_used_at, revoked_at
                FROM api_keys
                ORDER BY created_at DESC
                LIMIT 500
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def revoke_key(self, key_id: str) -> bool:
        now = _utc_now().isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE api_keys SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (now, key_id),
            )
        return cursor.rowcount == 1

    def authenticate_and_consume(
        self,
        raw_key: str,
        *,
        now: datetime | None = None,
    ) -> tuple[dict | None, bool, int]:
        """Return (key metadata, allowed, retry-after seconds)."""
        if not raw_key.startswith("aps_live_") or len(raw_key) > 160:
            return None, False, 0

        current = now or _utc_now()
        window_start = current.replace(second=0, microsecond=0)
        window_text = window_start.isoformat(timespec="seconds")
        reset_seconds = max(1, 60 - current.second)
        key_hash = self._hash(raw_key)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, name, key_prefix, requests_per_minute, revoked_at
                FROM api_keys WHERE key_hash = ?
                """,
                (key_hash,),
            ).fetchone()
            if row is None or row["revoked_at"] is not None:
                return None, False, 0

            connection.execute(
                """
                INSERT INTO api_key_usage (api_key_id, window_start, request_count)
                VALUES (?, ?, 1)
                ON CONFLICT(api_key_id, window_start)
                DO UPDATE SET request_count = request_count + 1
                """,
                (row["id"], window_text),
            )
            usage = connection.execute(
                """
                SELECT request_count FROM api_key_usage
                WHERE api_key_id = ? AND window_start = ?
                """,
                (row["id"], window_text),
            ).fetchone()
            connection.execute(
                "UPDATE api_keys SET last_used_at = ? WHERE id = ?",
                (current.isoformat(timespec="seconds"), row["id"]),
            )
            count = int(usage["request_count"])
            limit = int(row["requests_per_minute"])
            metadata = {
                "id": row["id"],
                "name": row["name"],
                "key_prefix": row["key_prefix"],
                "requests_per_minute": limit,
                "requests_used": count,
                "requests_remaining": max(0, limit - count),
                "reset_after": reset_seconds,
            }

            # Old minute buckets are operational data, not a permanent request log.
            connection.execute(
                "DELETE FROM api_key_usage WHERE window_start < ?",
                (window_start.replace(minute=0).isoformat(timespec="seconds"),),
            )

        return metadata, count <= limit, reset_seconds


def public_mode_enabled() -> bool:
    return os.getenv("APOKOLIPS_PUBLIC_MODE", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def configured_admin_token() -> str | None:
    token = os.getenv("APOKOLIPS_ADMIN_TOKEN", "")
    return token if len(token) >= 32 else None


def admin_token_matches(candidate: str | None, configured: str | None) -> bool:
    return bool(candidate and configured and hmac.compare_digest(candidate, configured))
