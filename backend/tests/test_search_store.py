from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.crawler.parsing import ExtractedDocument
from app.crawler.spider import CrawlIssue, CrawlReport
from app.search_store import SearchStore, build_fts_query
from app.main import create_app


def make_page(
    *,
    url: str,
    canonical_url: str | None = None,
    title: str = "",
    description: str = "",
    text: str = "",
    headings: tuple[str, ...] = (),
    language: str = "en",
    content_hash: str = "hash",
) -> ExtractedDocument:
    return ExtractedDocument(
        url=url,
        canonical_url=canonical_url or url,
        title=title,
        description=description,
        language=language,
        headings=headings,
        text=text,
        content_hash=content_hash,
        links=(),
    )


def test_store_initializes_fts5_and_empty_statistics(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()

    assert store.health() is True
    assert store.get_stats()["documents_indexed"] == 0
    assert store.get_stats()["index"] == "SQLite FTS5"


def test_weighted_bm25_prefers_title_matches_and_paginates(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    store.upsert_documents(
        [
            make_page(
                url="https://example.com/title-match",
                title="Python development handbook",
                description="A practical guide",
                text="Build reliable applications with useful examples.",
                content_hash="a",
            ),
            make_page(
                url="https://example.com/body-match",
                title="Application notes",
                text=("Python " * 12) + "database examples and tools.",
                content_hash="b",
            ),
            make_page(
                url="https://example.com/other",
                title="Cooking guide",
                text="Recipes and ingredients.",
                content_hash="c",
            ),
        ]
    )

    first_page = store.search("python", page=1, page_size=1)
    second_page = store.search("python", page=2, page_size=1)

    assert first_page["total_results"] == 2
    assert first_page["total_pages"] == 2
    assert first_page["has_more"] is True
    assert first_page["results"][0]["url"] == "https://example.com/title-match"
    assert first_page["results"][0]["relevance_score"] > 0
    assert second_page["results"][0]["url"] == "https://example.com/body-match"
    assert second_page["has_more"] is False


def test_documents_are_updated_without_creating_canonical_duplicates(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    store.upsert_documents(
        [
            make_page(
                url="https://example.com/old",
                canonical_url="https://example.com/canonical",
                title="Old document",
                text="obsolete text",
                content_hash="old",
            )
        ]
    )
    store.upsert_documents(
        [
            make_page(
                url="https://example.com/new",
                canonical_url="https://example.com/canonical",
                title="Updated document",
                text="fresh searchable marker",
                content_hash="new",
            )
        ]
    )

    result = store.search("marker")
    assert store.get_stats()["documents_indexed"] == 1
    assert result["total_results"] == 1
    assert result["results"][0]["url"] == "https://example.com/new"
    assert store.search("obsolete")["total_results"] == 0


def test_search_query_is_plain_text_not_raw_fts_syntax() -> None:
    assert build_fts_query("python OR sqlite") == '"python" AND "OR" AND "sqlite"'
    assert build_fts_query("Sinhala search") == '"Sinhala" AND "search"'

    with pytest.raises(ValueError):
        build_fts_query("   ")
    with pytest.raises(ValueError):
        build_fts_query("word " * 13)
    with pytest.raises(ValueError):
        build_fts_query("x" * 201)


def test_crawl_result_is_persisted_with_run_and_url_state(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    run_id = store.create_crawl_run(["https://example.com/"])
    page = make_page(
        url="https://example.com/",
        title="Phase Three Search",
        text="Durable index integration test",
        content_hash="phase-three",
    )
    report = CrawlReport(
        pages=(page,),
        issues=(
            CrawlIssue(
                "https://example.com/blocked",
                "robots_disallowed",
                "robots.txt does not permit this URL",
            ),
        ),
        processed_urls=2,
        discovered_urls=3,
        elapsed_seconds=1.25,
    )

    indexed = store.save_crawl_result(run_id, report)
    run = store.get_crawl_run(run_id)
    stats = store.get_stats()

    assert indexed == 1
    assert run is not None
    assert run["status"] == "completed"
    assert run["processed_urls"] == 2
    assert run["discovered_urls"] == 3
    assert run["indexed_pages"] == 1
    assert run["issue_count"] == 1
    assert run["seeds"] == ["https://example.com/"]
    assert stats["documents_indexed"] == 1
    assert stats["tracked_urls"] == 2
    assert store.search("integration")["total_results"] == 1


def test_failed_crawl_run_is_recorded(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    run_id = store.create_crawl_run(["https://example.com/"])
    store.fail_crawl_run(run_id, "test failure")

    run = store.get_crawl_run(run_id)
    assert run is not None
    assert run["status"] == "failed"
    assert run["error_message"] == "test failure"


def test_search_api_reads_only_the_local_index_and_returns_stats(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    store.upsert_documents(
        [
            make_page(
                url="https://example.com/local",
                title="Apokolips own search index",
                text="First party database-backed search",
                content_hash="local",
            )
        ]
    )
    test_app = create_app(store)

    with TestClient(test_app) as client:
        health = client.get("/health")
        response = client.get("/search", params={"q": "Apokolips search"})
        stats = client.get("/stats")

    assert health.status_code == 200
    assert health.json()["index"] == "SQLite FTS5"
    assert response.status_code == 200
    assert response.json()["total_results"] == 1
    assert response.json()["results"][0]["url"] == "https://example.com/local"
    assert stats.json()["documents_indexed"] == 1


def test_crawl_api_persists_spider_output(monkeypatch, tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    page = make_page(
        url="https://example.com/crawled",
        title="Crawled and indexed",
        text="A unique persistence token",
        content_hash="api-crawl",
    )

    class FakeSpider:
        def __init__(self, _config) -> None:
            pass

        async def crawl(self, _seeds: list[str]) -> CrawlReport:
            return CrawlReport(
                pages=(page,),
                issues=(),
                processed_urls=1,
                discovered_urls=1,
                elapsed_seconds=0.01,
            )

    monkeypatch.setattr(main_module, "ApokolipsSpider", FakeSpider)
    test_app = create_app(store)

    with TestClient(test_app) as client:
        response = client.post(
            "/crawl",
            json={"seeds": ["https://example.com/"], "max_pages": 1, "max_depth": 0},
        )
        indexed_search = client.get("/search", params={"q": "persistence token"})

    assert response.status_code == 200
    assert response.json()["indexed_pages"] == 1
    assert response.json()["persistence"] == "saved_to_local_database"
    assert indexed_search.status_code == 200
    assert indexed_search.json()["total_results"] == 1


def test_search_api_rejects_invalid_pagination_and_query(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    test_app = create_app(store)

    with TestClient(test_app) as client:
        blank_query = client.get("/search", params={"q": "   "})
        huge_page_size = client.get("/search", params={"q": "word", "page_size": 1000})

    assert blank_query.status_code == 422
    assert huge_page_size.status_code == 422
