from __future__ import annotations

import asyncio

import httpx

from app.brave_search import BraveSearchClient, ClientSearchRateLimiter
from app.main import create_app


def api_request(app, path: str, params: dict[str, str]):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, params=params)

    return asyncio.run(send_request())


class FakeBraveSearchClient:
    is_configured = True

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> dict:
        self.calls.append((query, page, page_size))
        return {
            "provider": "Brave Search",
            "query": query,
            "page": page,
            "page_size": page_size,
            "result_count": 1,
            "has_more": page < 2,
            "results": [
                {
                    "title": "Apokolips example",
                    "url": "https://example.com/apokolips",
                    "display_url": "example.com",
                    "description": "A result returned by a mocked provider.",
                }
            ],
        }


def test_result_normalisation_rejects_non_web_urls() -> None:
    payload = {
        "web": {
            "results": [
                {
                    "title": "Valid result",
                    "url": "https://example.com/path",
                    "description": "A description",
                    "profile": {"long_name": "Example"},
                },
                {"title": "Unsafe result", "url": "javascript:alert(1)"},
                {"title": "Missing host", "url": "https:///missing-host"},
                {"title": "Missing URL"},
            ]
        }
    }

    results = BraveSearchClient._normalise_results(payload)

    assert len(results) == 1
    assert results[0] == {
        "title": "Valid result",
        "url": "https://example.com/path",
        "display_url": "Example",
        "description": "A description",
    }


def test_rate_limiter_blocks_after_configured_limit() -> None:
    limiter = ClientSearchRateLimiter(requests_per_minute=2)

    assert limiter.consume("127.0.0.1")[0] is True
    assert limiter.consume("127.0.0.1")[0] is True
    allowed, retry_after = limiter.consume("127.0.0.1")
    assert allowed is False
    assert retry_after >= 1
    assert limiter.consume("192.0.2.1")[0] is True


def test_web_search_endpoint_uses_provider_and_returns_no_store_header() -> None:
    provider = FakeBraveSearchClient()
    app = create_app(brave_search_client=provider)

    response = api_request(
        app,
        "/api/v1/web-search",
        {"q": "  Apokolips search  ", "page": "2", "page_size": "5"},
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["provider"] == "Brave Search"
    assert response.json()["results"][0]["url"] == "https://example.com/apokolips"
    assert provider.calls == [("Apokolips search", 2, 5)]


def test_web_search_endpoint_validates_empty_and_too_long_queries() -> None:
    app = create_app(brave_search_client=FakeBraveSearchClient())

    empty = api_request(app, "/api/v1/web-search", {"q": "   "})
    too_many_words = api_request(
        app,
        "/api/v1/web-search",
        {"q": " ".join(["word"] * 76)},
    )

    assert empty.status_code == 422
    assert too_many_words.status_code == 422
