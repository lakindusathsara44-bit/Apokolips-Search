"""FastAPI application for the Apokolips Search local development server."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .api_access import (
    APIKeyStore,
    admin_token_matches,
    configured_admin_token,
    public_mode_enabled,
)
from .brave_search import (
    BraveSearchClient,
    ClientSearchRateLimiter,
    SearchProviderError,
    SearchProviderNotConfigured,
    SearchProviderRateLimited,
)
from .crawl_queue import CrawlQueue
from .crawl_worker import run_crawl_worker
from .crawler import ApokolipsSpider, CrawlConfig
from .search_store import SearchStore


class CrawlRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=10)
    max_pages: int = Field(default=5, ge=1, le=25)
    max_depth: int = Field(default=1, ge=0, le=3)


class CrawlJobRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=10)
    max_pages: int = Field(default=5, ge=1, le=25)
    max_depth: int = Field(default=1, ge=0, le=3)


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    requests_per_minute: int = Field(default=60, ge=1, le=600)


def create_app(
    search_store: SearchStore | None = None,
    crawl_queue: CrawlQueue | None = None,
    api_key_store: APIKeyStore | None = None,
    brave_search_client: BraveSearchClient | None = None,
) -> FastAPI:
    """Application factory; tests may inject isolated database components."""
    store = search_store or SearchStore()
    queue = crawl_queue or CrawlQueue(store.database_path)
    key_store = api_key_store or APIKeyStore(store.database_path)
    brave_client = brave_search_client or BraveSearchClient()
    web_search_limiter = ClientSearchRateLimiter(requests_per_minute=30)
    is_public = public_mode_enabled()
    admin_token = configured_admin_token()

    def check_admin_token(authorization: str | None) -> None:
        candidate = (
            authorization[7:].strip()
            if authorization and authorization.lower().startswith("bearer ")
            else None
        )
        if not admin_token_matches(candidate, admin_token):
            raise HTTPException(
                status_code=401,
                detail="A valid administrator bearer token is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def require_admin(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> None:
        check_admin_token(authorization)

    def require_crawler_admin(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> None:
        if is_public:
            check_admin_token(authorization)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        await asyncio.to_thread(store.initialize)
        if is_public and admin_token is None:
            raise RuntimeError(
                "APOKOLIPS_PUBLIC_MODE requires APOKOLIPS_ADMIN_TOKEN "
                "to contain at least 32 characters"
            )
        await asyncio.to_thread(queue.initialize)
        await asyncio.to_thread(key_store.initialize)
        worker_task = asyncio.create_task(run_crawl_worker(store, queue))
        _app.state.crawl_worker_task = worker_task
        try:
            yield
        finally:
            worker_task.cancel()
            await asyncio.gather(worker_task, return_exceptions=True)

    api = FastAPI(
        title="Apokolips Search API",
        version="0.6.0",
        description=(
            "Apokolips Search provides a Level 1 Brave-powered web search proxy and a "
            "separate API-key authenticated first-party SQLite FTS5 search index. "
            "Crawler and management endpoints remain administrator-controlled."
        ),
        lifespan=lifespan,
    )
    api.state.search_store = store
    api.state.crawl_queue = queue
    api.state.api_key_store = key_store
    api.state.brave_search_client = brave_client
    api.state.web_search_limiter = web_search_limiter

    configured_origins = os.getenv(
        "APOKOLIPS_CORS_ORIGINS",
        "http://127.0.0.1:5173,http://localhost:5173",
    )
    allowed_origins = [
        origin.strip().rstrip("/")
        for origin in configured_origins.split(",")
        if origin.strip() and origin.strip() != "*"
    ]
    api.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
        expose_headers=[
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "Retry-After",
        ],
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
            "version": "0.6.0",
            "database": "ready",
            "index": "SQLite FTS5",
        }

    @api.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {
            "message": "Apokolips Search API",
            "docs": "/docs",
            "search": "/api/v1/search?q=your+query",
            "web_search": "/api/v1/web-search?q=your+query",
            "api_version": "v1",
        }

    @api.post(
        "/crawl",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    async def crawl(request: CrawlRequest) -> dict:
        """Run a bounded crawl immediately and persist its extracted pages."""
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
        except Exception as exc:
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

    @api.post(
        "/crawl/jobs",
        status_code=202,
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    async def enqueue_crawl_job(request: CrawlJobRequest) -> dict:
        """Queue a crawl to be processed in the background by Apokolips Spider."""
        try:
            job = await asyncio.to_thread(
                queue.enqueue,
                request.seeds,
                request.max_pages,
                request.max_depth,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"job": job}

    @api.get(
        "/crawl/jobs",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    async def crawl_jobs(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict:
        jobs = await asyncio.to_thread(queue.list_jobs, limit)
        return {"jobs": jobs}

    @api.get(
        "/crawl/jobs/{job_id}",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    async def crawl_job(job_id: str) -> dict:
        job = await asyncio.to_thread(queue.get_job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Crawl job not found")
        return {"job": job}

    @api.post(
        "/crawl/jobs/{job_id}/cancel",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    async def cancel_crawl_job(job_id: str) -> dict:
        job = await asyncio.to_thread(queue.get_job, job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Crawl job not found")
        cancelled = await asyncio.to_thread(queue.cancel_pending, job_id)
        if not cancelled:
            raise HTTPException(
                status_code=409,
                detail="Only pending crawl jobs can be cancelled",
            )
        updated_job = await asyncio.to_thread(queue.get_job, job_id)
        return {"job": updated_job}

    @api.get("/search", tags=["search"])
    def search(
        q: str = Query(min_length=1, max_length=200, description="Search terms"),
        page: int = Query(default=1, ge=1, le=10_000),
        page_size: int = Query(default=10, ge=1, le=50),
    ) -> dict:
        """Local-development search endpoint; disabled in public deployment mode."""
        if is_public:
            raise HTTPException(
                status_code=404,
                detail="Use the authenticated /api/v1/search endpoint",
            )
        try:
            return store.search(q, page=page, page_size=page_size)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @api.get(
        "/api/v1/search",
        tags=["public search"],
        summary="Search the Apokolips first-party web index",
        description=(
            "Requires an active API key in the X-API-Key header. Each key has an "
            "independent per-minute quota. Results come only from pages indexed by "
            "Apokolips Spider; this endpoint does not proxy another search provider."
        ),
    )
    async def public_search(
        response: Response,
        q: str = Query(min_length=1, max_length=200, description="Search terms"),
        page: int = Query(default=1, ge=1, le=10_000),
        page_size: int = Query(default=10, ge=1, le=20),
        x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    ) -> dict:
        if not x_api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing API key. Send it in the X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        key_info, allowed, reset_after = await asyncio.to_thread(
            key_store.authenticate_and_consume,
            x_api_key,
        )
        if key_info is None:
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )
        response.headers["X-RateLimit-Limit"] = str(key_info["requests_per_minute"])
        response.headers["X-RateLimit-Remaining"] = str(key_info["requests_remaining"])
        response.headers["X-RateLimit-Reset"] = str(reset_after)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="API rate limit exceeded. Retry after the current minute window.",
                headers={
                    "Retry-After": str(reset_after),
                    "X-RateLimit-Limit": str(key_info["requests_per_minute"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_after),
                },
            )
        try:
            result = await asyncio.to_thread(
                store.search,
                q,
                page=page,
                page_size=page_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "api_version": "v1",
            "engine": "Apokolips Search",
            **result,
        }

    @api.get(
        "/api/v1/web-search",
        tags=["web search"],
        summary="Search the public web through Brave Search",
        description=(
            "Level 1 web search proxy. The Brave API key stays on the server; "
            "provider results are returned transiently and are not stored in the Apokolips index."
        ),
    )
    async def web_search(
        request: Request,
        response: Response,
        q: str = Query(min_length=1, max_length=600, description="Web search terms"),
        page: int = Query(default=1, ge=1, le=10),
        page_size: int = Query(default=10, ge=1, le=20),
    ) -> dict:
        query = q.strip()
        if not query or len(query.split()) > 75:
            raise HTTPException(
                status_code=422,
                detail="Query must contain 1–600 non-space characters and no more than 75 words.",
            )

        client_key = request.client.host if request.client else "unknown"
        allowed, retry_after = web_search_limiter.consume(client_key)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail="Search request limit reached. Please retry after the current minute window.",
                headers={"Retry-After": str(retry_after)},
            )

        try:
            result = await brave_client.search(query, page=page, page_size=page_size)
        except SearchProviderNotConfigured as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None
        except SearchProviderRateLimited as exc:
            raise HTTPException(
                status_code=503,
                detail="The upstream search provider is temporarily rate-limited. Please retry shortly.",
                headers={"Retry-After": "60"},
            ) from exc
        except SearchProviderError:
            raise HTTPException(
                status_code=502,
                detail="The upstream search provider could not complete the request.",
            ) from None

        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return result

    @api.post(
        "/admin/api-keys",
        status_code=201,
        tags=["API key administration"],
        dependencies=[Depends(require_admin)],
        summary="Create an API key (administrator only)",
    )
    def create_api_key(request: CreateAPIKeyRequest) -> dict:
        try:
            created = key_store.create_key(
                request.name,
                request.requests_per_minute,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "message": "Copy this API key now. It will not be shown again.",
            "key": created,
        }

    @api.get(
        "/admin/api-keys",
        tags=["API key administration"],
        dependencies=[Depends(require_admin)],
        summary="List API keys without exposing their secrets",
    )
    def list_api_keys() -> dict:
        return {"keys": key_store.list_keys()}

    @api.delete(
        "/admin/api-keys/{key_id}",
        tags=["API key administration"],
        dependencies=[Depends(require_admin)],
        summary="Revoke an API key",
    )
    def revoke_api_key(key_id: str) -> dict:
        if not key_store.revoke_key(key_id):
            raise HTTPException(status_code=404, detail="Active API key not found")
        return {"status": "revoked", "key_id": key_id}

    @api.get(
        "/stats",
        tags=["system"],
        dependencies=[Depends(require_crawler_admin)],
    )
    def stats() -> dict:
        """Return local index and crawl statistics."""
        return store.get_stats()

    @api.get(
        "/crawl/runs",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    def crawl_runs(
        limit: int = Query(default=20, ge=1, le=100),
    ) -> dict:
        return {"runs": store.list_crawl_runs(limit=limit)}

    @api.get(
        "/crawl/runs/{run_id}",
        tags=["crawler"],
        dependencies=[Depends(require_crawler_admin)],
    )
    def crawl_run(run_id: str) -> dict:
        run = store.get_crawl_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Crawl run not found")
        return run

    return api


app = create_app()
