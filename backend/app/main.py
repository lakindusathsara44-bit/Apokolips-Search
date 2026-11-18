"""FastAPI application for the Apokolips Search local development server."""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .crawler import ApokolipsSpider, CrawlConfig
from .search_store import SearchStore


class CrawlRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=10)
    max_pages: int = Field(default=5, ge=1, le=25)
    max_depth: int = Field(default=1, ge=0, le=3)


def create_app(search_store: SearchStore | None = None) -> FastAPI:
    """Application factory; tests may inject a temporary isolated database."""
    store = search_store or SearchStore()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(store.initialize)
        yield

    api = FastAPI(
        title="Apokolips Search API",
        version="0.3.0",
        description=(
            "Independent local-first search API. Apokolips Spider discovers permitted "
            "pages, SQLite stores crawl metadata, and SQLite FTS5 ranks the first-party index."
        ),
        lifespan=lifespan,
    )
    api.state.search_store = store

    api.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @api.get("/health", tags=["system"])
    def health() -> dict[str, str]:
        try:
            store.health()
        except (OSError, RuntimeError, ValueError, sqlite3.Error):
            raise HTTPException(status_code=503, detail="Search database is unavailable") from None
        return {
            "status": "ok",
            "service": "apokolips-search-api",
            "version": "0.3.0",
            "database": "ready",
            "index": "SQLite FTS5",
        }

    @api.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "message": "Apokolips Search API",
            "docs": "/docs",
            "search": "/search?q=your+query",
        }

    @api.post("/crawl", tags=["crawler"])
    async def crawl(request: CrawlRequest) -> dict:
        """Crawl permitted URLs, persist extracted documents, and update the local index."""
        run_id = await asyncio.to_thread(store.create_crawl_run, request.seeds)
        spider = ApokolipsSpider(
            CrawlConfig(
                max_pages=request.max_pages,
                max_depth=request.max_depth,
            )
        )
        try:
            report = await asyncio.wait_for(spider.crawl(request.seeds), timeout=120)
            indexed_count = await asyncio.to_thread(
                store.save_crawl_result,
                run_id,
                report,
            )
        except TimeoutError as exc:
            await asyncio.to_thread(
                store.fail_crawl_run,
                run_id,
                "Crawl exceeded the 120-second request limit",
            )
            raise HTTPException(
                status_code=504,
                detail="Crawl exceeded the 120-second request limit",
            ) from exc
        except ValueError as exc:
            await asyncio.to_thread(store.fail_crawl_run, run_id, str(exc))
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - mark and report any unexpected crawl failure
            await asyncio.to_thread(
                store.fail_crawl_run,
                run_id,
                "The crawl or database operation failed",
            )
            raise HTTPException(
                status_code=500,
                detail="The crawl could not be completed. Check the crawl run record.",
            ) from exc

        return {
            "status": "completed",
            "run_id": run_id,
            "processed_urls": report.processed_urls,
            "discovered_urls": report.discovered_urls,
            "indexed_pages": indexed_count,
            "issue_count": len(report.issues),
            "elapsed_seconds": report.elapsed_seconds,
            "pages": [
                {
                    "url": page.url,
                    "canonical_url": page.canonical_url,
                    "title": page.title,
                    "links_found": len(page.links),
                }
                for page in report.pages
            ],
            "issues": [
                {"url": issue.url, "code": issue.code, "message": issue.message}
                for issue in report.issues
            ],
            "persistence": "saved_to_local_database",
        }

    @api.get("/search", tags=["search"])
    def search(
        q: str = Query(min_length=1, max_length=200, description="Search terms"),
        page: int = Query(default=1, ge=1, le=10_000),
        page_size: int = Query(default=10, ge=1, le=50),
    ) -> dict:
        """Search Apokolips' own SQLite FTS5 index using weighted BM25 ranking."""
        try:
            return store.search(q, page=page, page_size=page_size)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.get("/stats", tags=["system"])
    def stats() -> dict:
        """Return local index and crawl statistics."""
        return store.get_stats()

    @api.get("/crawl/runs", tags=["crawler"])
    def crawl_runs(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict:
        return {"runs": store.list_crawl_runs(limit=limit)}

    @api.get("/crawl/runs/{run_id}", tags=["crawler"])
    def crawl_run(run_id: str) -> dict:
        run = store.get_crawl_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Crawl run not found")
        return run

    return api


app = create_app()
