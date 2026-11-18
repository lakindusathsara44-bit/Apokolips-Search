"""FastAPI application for the Apokolips Search local development server."""
import asyncio

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .crawler import ApokolipsSpider, CrawlConfig

app = FastAPI(
    title="Apokolips Search API",
    version="0.2.0",
    description=(
        "Local-first API for Apokolips Search. Phase 02 adds a bounded, "
        "robots-aware crawler; fetched pages are returned but not persisted yet."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

class CrawlRequest(BaseModel):
    seeds: list[str] = Field(min_length=1, max_length=10)
    max_pages: int = Field(default=5, ge=1, le=25)
    max_depth: int = Field(default=1, ge=0, le=3)

@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "apokolips-search-api", "version": "0.2.0"}

@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "Apokolips Search API", "docs": "/docs"}

@app.post("/crawl", tags=["crawler"])
async def crawl(request: CrawlRequest) -> dict:
    """Crawl up to 25 URLs and return extracted pages; no data is stored yet."""
    spider = ApokolipsSpider(CrawlConfig(
        max_pages=request.max_pages,
        max_depth=request.max_depth,
    ))
    try:
        report = await asyncio.wait_for(spider.crawl(request.seeds), timeout=120)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=504, detail="Crawl exceeded the 120-second request limit"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "status": "completed",
        "processed_urls": report.processed_urls,
        "discovered_urls": report.discovered_urls,
        "elapsed_seconds": report.elapsed_seconds,
        "pages": [
            {
                "url": page.url,
                "canonical_url": page.canonical_url,
                "title": page.title,
                "description": page.description,
                "language": page.language,
                "headings": list(page.headings),
                "text": page.text,
                "content_hash": page.content_hash,
                "links_found": len(page.links),
            }
            for page in report.pages
        ],
        "issues": [
            {"url": issue.url, "code": issue.code, "message": issue.message}
            for issue in report.issues
        ],
        "persistence": "not_configured",
    }
