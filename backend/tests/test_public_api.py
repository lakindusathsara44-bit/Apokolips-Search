from __future__ import annotations

import asyncio
import sqlite3

import httpx
import pytest

from app.api_access import APIKeyStore
from app.main import create_app
from app.search_store import SearchStore
from app.crawler.parsing import ExtractedDocument


ADMIN_TOKEN = "test-admin-token-that-is-long-enough-for-production"


def api_request(app, method: str, path: str, **kwargs):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send_request())


def make_search_store(tmp_path) -> SearchStore:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    store.upsert_documents(
        [
            ExtractedDocument(
                url="https://example.com/apokolips",
                canonical_url="https://example.com/apokolips",
                title="Apokolips public search API",
                description="A first party search API example",
                language="en",
                headings=("Developer API",),
                text="Search the Apokolips independent web index using a developer key.",
                content_hash="public-api-fixture",
                links=(),
            )
        ]
    )
    return store


def test_api_key_secret_is_returned_once_and_only_hash_is_stored(tmp_path) -> None:
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    store.initialize()
    created = store.create_key("Docs integration", requests_per_minute=25)

    assert created["api_key"].startswith("aps_live_")
    assert created["requests_per_minute"] == 25
    assert "key_hash" not in created
    assert store.list_keys()[0]["key_prefix"] == created["key_prefix"]

    with sqlite3.connect(store.database_path) as connection:
        stored_hash = connection.execute(
            "SELECT key_hash FROM api_keys WHERE id = ?",
            (created["id"],),
        ).fetchone()[0]
    assert stored_hash != created["api_key"]
    assert len(stored_hash) == 64


def test_key_name_and_quota_are_validated(tmp_path) -> None:
    store = APIKeyStore(tmp_path / "keys.sqlite3")
    store.initialize()

    with pytest.raises(ValueError):
        store.create_key(" ")
    with pytest.raises(ValueError):
        store.create_key("too many", requests_per_minute=601)


def test_api_key_quota_is_per_key_and_resets_each_minute(tmp_path) -> None:
    from datetime import UTC, datetime, timedelta

    store = APIKeyStore(tmp_path / "keys.sqlite3")
    store.initialize()
    first = store.create_key("first", requests_per_minute=2)
    second = store.create_key("second", requests_per_minute=2)
    now = datetime(2026, 11, 18, 10, 20, 15, tzinfo=UTC)

    key_info, allowed, _ = store.authenticate_and_consume(first["api_key"], now=now)
    assert allowed is True
    assert key_info["requests_remaining"] == 1
    assert store.authenticate_and_consume(first["api_key"], now=now)[1] is True
    assert store.authenticate_and_consume(first["api_key"], now=now)[1] is False
    assert store.authenticate_and_consume(second["api_key"], now=now)[1] is True
    assert store.authenticate_and_consume(
        first["api_key"],
        now=now + timedelta(minutes=1),
    )[1] is True


def test_public_search_requires_valid_key_and_returns_first_party_results(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("APOKOLIPS_PUBLIC_MODE", "true")
    monkeypatch.setenv("APOKOLIPS_ADMIN_TOKEN", ADMIN_TOKEN)
    search = make_search_store(tmp_path)
    keys = APIKeyStore(search.database_path)
    keys.initialize()
    created = keys.create_key("test integration")
    app = create_app(search, api_key_store=keys)

    missing = api_request(app, "GET", "/api/v1/search", params={"q": "Apokolips"})
    invalid = api_request(
        app,
        "GET",
        "/api/v1/search",
        params={"q": "Apokolips"},
        headers={"X-API-Key": "aps_live_invalid"},
    )
    response = api_request(
        app,
        "GET",
        "/api/v1/search",
        params={"q": "Apokolips public"},
        headers={"X-API-Key": created["api_key"]},
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert response.status_code == 200
    assert response.json()["api_version"] == "v1"
    assert response.json()["engine"] == "Apokolips Search"
    assert response.json()["total_results"] == 1
    assert response.json()["results"][0]["url"] == "https://example.com/apokolips"
    assert response.headers["x-ratelimit-limit"] == "60"
    assert response.headers["x-ratelimit-remaining"] == "59"


def test_public_search_enforces_per_key_rate_limit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APOKOLIPS_PUBLIC_MODE", "true")
    monkeypatch.setenv("APOKOLIPS_ADMIN_TOKEN", ADMIN_TOKEN)
    search = make_search_store(tmp_path)
    keys = APIKeyStore(search.database_path)
    keys.initialize()
    created = keys.create_key("one request", requests_per_minute=1)
    app = create_app(search, api_key_store=keys)
    headers = {"X-API-Key": created["api_key"]}

    first = api_request(
        app,
        "GET",
        "/api/v1/search",
        params={"q": "Apokolips"},
        headers=headers,
    )
    second = api_request(
        app,
        "GET",
        "/api/v1/search",
        params={"q": "Apokolips"},
        headers=headers,
    )

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.headers["retry-after"]
    assert second.headers["x-ratelimit-remaining"] == "0"


def test_admin_can_create_list_and_revoke_keys(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APOKOLIPS_PUBLIC_MODE", "true")
    monkeypatch.setenv("APOKOLIPS_ADMIN_TOKEN", ADMIN_TOKEN)
    search = make_search_store(tmp_path)
    keys = APIKeyStore(search.database_path)
    keys.initialize()
    app = create_app(search, api_key_store=keys)
    unauthorized = api_request(
        app,
        "POST",
        "/admin/api-keys",
        json={"name": "external app"},
    )
    auth = {"Authorization": f"Bearer {ADMIN_TOKEN}"}

    created = api_request(
        app,
        "POST",
        "/admin/api-keys",
        headers=auth,
        json={"name": "external app", "requests_per_minute": 30},
    )
    key_id = created.json()["key"]["id"]
    raw_key = created.json()["key"]["api_key"]
    listed = api_request(app, "GET", "/admin/api-keys", headers=auth)
    revoked = api_request(app, "DELETE", f"/admin/api-keys/{key_id}", headers=auth)
    rejected_after_revoke = api_request(
        app,
        "GET",
        "/api/v1/search",
        params={"q": "Apokolips"},
        headers={"X-API-Key": raw_key},
    )

    assert unauthorized.status_code == 401
    assert created.status_code == 201
    assert "api_key" not in listed.json()["keys"][0]
    assert listed.json()["keys"][0]["requests_per_minute"] == 30
    assert revoked.status_code == 200
    assert rejected_after_revoke.status_code == 401


def test_public_mode_hides_legacy_search_and_protects_crawler_controls(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("APOKOLIPS_PUBLIC_MODE", "true")
    monkeypatch.setenv("APOKOLIPS_ADMIN_TOKEN", ADMIN_TOKEN)
    search = make_search_store(tmp_path)
    keys = APIKeyStore(search.database_path)
    keys.initialize()
    app = create_app(search, api_key_store=keys)

    legacy_search = api_request(app, "GET", "/search", params={"q": "Apokolips"})
    crawl = api_request(
        app,
        "POST",
        "/crawl/jobs",
        json={"seeds": ["https://example.com/"]},
    )
    admin_crawl = api_request(
        app,
        "POST",
        "/crawl/jobs",
        headers={"Authorization": f"Bearer {ADMIN_TOKEN}"},
        json={"seeds": ["https://example.com/"]},
    )

    assert legacy_search.status_code == 404
    assert crawl.status_code == 401
    assert admin_crawl.status_code == 202


def test_public_mode_startup_requires_a_strong_admin_token(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APOKOLIPS_PUBLIC_MODE", "true")
    monkeypatch.delenv("APOKOLIPS_ADMIN_TOKEN", raising=False)
    app = create_app(
        SearchStore(tmp_path / "search.sqlite3"),
        api_key_store=APIKeyStore(tmp_path / "search.sqlite3"),
    )

    async def run_lifespan():
        async with app.router.lifespan_context(app):
            pass

    with pytest.raises(RuntimeError, match="APOKOLIPS_ADMIN_TOKEN"):
        asyncio.run(run_lifespan())
