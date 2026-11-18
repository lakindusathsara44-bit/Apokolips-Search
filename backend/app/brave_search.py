"""Brave Search API adapter for Level 1 web search.

Search responses are normalized in memory and are never written to the local index.
"""

from __future__ import annotations

import asyncio
import math
import os
import threading
import time
from urllib.parse import urlsplit

import aiohttp

BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class SearchProviderError(RuntimeError):
    """Base error for an upstream search provider failure."""


class SearchProviderNotConfigured(SearchProviderError):
    """The provider API key is missing or has been rejected."""


class SearchProviderRateLimited(SearchProviderError):
    """The upstream provider has rejected a request due to its quota."""


class BraveSearchClient:
    """Small, stateless client for Brave's human-oriented Web Search API."""

    def __init__(
        self,
        api_key: str | None = None,
        country: str | None = None,
        timeout_seconds: float = 12.0,
    ) -> None:
        configured_key = api_key if api_key is not None else os.getenv("BRAVE_SEARCH_API_KEY", "")
        self.api_key = configured_key.strip()
        configured_country = country if country is not None else os.getenv(
            "BRAVE_SEARCH_COUNTRY", "LK"
        )
        country_code = configured_country.strip().upper()
        self.country = country_code if len(country_code) == 2 and country_code.isalpha() else "LK"
        self.timeout_seconds = timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _normalise_results(payload: dict) -> list[dict[str, str]]:
        web_data = payload.get("web")
        raw_results = web_data.get("results", []) if isinstance(web_data, dict) else []
        normalised: list[dict[str, str]] = []

        if not isinstance(raw_results, list):
            return normalised

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            raw_url = item.get("url")
            title = item.get("title")
            if not isinstance(raw_url, str) or not isinstance(title, str):
                continue

            try:
                parsed = urlsplit(raw_url)
            except ValueError:
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                continue

            description = item.get("description", "")
            profile = item.get("profile")
            long_name = profile.get("long_name") if isinstance(profile, dict) else ""
            display_url = long_name if isinstance(long_name, str) and long_name else parsed.hostname

            normalised.append(
                {
                    "title": title[:500],
                    "url": raw_url,
                    "display_url": display_url[:200],
                    "description": description[:2000]
                    if isinstance(description, str)
                    else "",
                }
            )

        return normalised

    async def search(self, query: str, page: int = 1, page_size: int = 10) -> dict:
        """Fetch one page of current web results; do not cache or persist the response."""
        if not self.is_configured:
            raise SearchProviderNotConfigured(
                "Web search is not configured. Add BRAVE_SEARCH_API_KEY to the backend environment."
            )

        params = {
            "q": query,
            "country": self.country,
            "count": page_size,
            "offset": page - 1,
            "safesearch": "moderate",
            "text_decorations": "false",
            "result_filter": "web",
        }
        timeout = aiohttp.ClientTimeout(
            total=self.timeout_seconds,
            connect=min(5.0, self.timeout_seconds),
        )

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    BRAVE_WEB_SEARCH_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": self.api_key,
                    },
                ) as response:
                    if response.status in {401, 403}:
                        raise SearchProviderNotConfigured(
                            "The configured web search provider credentials were rejected."
                        )
                    if response.status == 429:
                        raise SearchProviderRateLimited(
                            "The web search provider rate limit has been reached."
                        )
                    if response.status != 200:
                        raise SearchProviderError(
                            f"The web search provider returned HTTP {response.status}."
                        )
                    try:
                        payload = await response.json(content_type=None)
                    except (aiohttp.ContentTypeError, ValueError) as exc:
                        raise SearchProviderError(
                            "The web search provider returned an invalid response."
                        ) from exc
        except SearchProviderError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise SearchProviderError(
                "The web search provider could not be reached. Please try again."
            ) from exc

        if not isinstance(payload, dict):
            raise SearchProviderError("The web search provider returned an invalid response.")

        query_data = payload.get("query")
        more_available = (
            query_data.get("more_results_available", False)
            if isinstance(query_data, dict)
            else False
        )
        results = self._normalise_results(payload)

        return {
            "provider": "Brave Search",
            "query": query,
            "page": page,
            "page_size": page_size,
            "result_count": len(results),
            "has_more": bool(more_available),
            "results": results,
        }


class ClientSearchRateLimiter:
    """Small per-process IP limiter to protect the provider key from accidental abuse."""

    def __init__(self, requests_per_minute: int = 30) -> None:
        self.requests_per_minute = requests_per_minute
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def consume(self, client_key: str) -> tuple[bool, int]:
        now = time.monotonic()
        with self._lock:
            current = self._windows.get(client_key)
            if current is None or now - current[0] >= 60:
                self._windows[client_key] = (now, 1)
                allowed, retry_after = True, 60
            elif current[1] >= self.requests_per_minute:
                allowed = False
                retry_after = max(1, math.ceil(60 - (now - current[0])))
            else:
                self._windows[client_key] = (current[0], current[1] + 1)
                allowed = True
                retry_after = max(1, math.ceil(60 - (now - current[0])))

            # Bound memory use on a long-running single-instance deployment.
            if len(self._windows) > 5000:
                self._windows = {
                    key: window
                    for key, window in self._windows.items()
                    if now - window[0] < 60
                }

        return allowed, retry_after
