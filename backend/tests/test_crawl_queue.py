from __future__ import annotations

import asyncio
import sqlite3

import httpx

from app.crawl_queue import CrawlQueue
from app.crawl_worker import process_next_job
from app.crawler.parsing import ExtractedDocument
from app.crawler.spider import CrawlReport
from app.main import create_app
from app.search_store import SearchStore


def api_request(app, method: str, path: str, **kwargs):
    async def send_request():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send_request())


def make_page() -> ExtractedDocument:
    return ExtractedDocument(
        url="https://example.com/durable-queue",
        canonical_url="https://example.com/durable-queue",
        title="Durable queue marker page",
        description="Background crawler persistence test",
        language="en",
        headings=("Crawl jobs",),
        text="This page verifies that background jobs are indexed.",
        content_hash="durable-queue-test",
        links=(),
    )


def test_enqueue_and_atomic_claim_persist_job_state(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()

    created = queue.enqueue(["https://example.com/"], max_pages=4, max_depth=2)
    assert created["status"] == "pending"
    assert created["seeds"] == ["https://example.com/"]
    assert created["attempts"] == 0

    claimed = queue.claim_next_job("worker-one")
    assert claimed is not None
    assert claimed["id"] == created["id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert claimed["worker_id"] == "worker-one"
    assert queue.claim_next_job("worker-two") is None


def test_expired_worker_lease_returns_job_to_queue(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    created = queue.enqueue(["https://example.com/"])
    first_claim = queue.claim_next_job("worker-one")
    assert first_claim is not None

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE crawl_jobs SET lease_expires_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", created["id"]),
        )

    second_claim = queue.claim_next_job("worker-two")
    assert second_claim is not None
    assert second_claim["id"] == created["id"]
    assert second_claim["attempts"] == 2
    assert second_claim["worker_id"] == "worker-two"


def test_failed_jobs_retry_then_become_terminal(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    created = queue.enqueue(["https://example.com/"], max_attempts=2)

    first = queue.claim_next_job("worker-one")
    assert first is not None
    retried = queue.fail(created["id"], "worker-one", "temporary failure")
    assert retried is not None
    assert retried["status"] == "pending"
    assert retried["error_message"] == "temporary failure"

    second = queue.claim_next_job("worker-two")
    assert second is not None
    terminal = queue.fail(created["id"], "worker-two", "second failure")
    assert terminal is not None
    assert terminal["status"] == "failed"
    assert terminal["attempts"] == 2
    assert terminal["finished_at"] is not None


def test_only_pending_jobs_can_be_cancelled(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    pending = queue.enqueue(["https://example.com/pending"])
    running = queue.enqueue(["https://example.com/running"])
    queue.claim_next_job("worker-one")

    assert queue.cancel_pending(pending["id"]) is True
    assert queue.get_job(pending["id"])["status"] == "cancelled"
    assert queue.cancel_pending(running["id"]) is False


def test_queue_api_enqueues_reads_and_cancels_jobs(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    test_app = create_app(store, queue)

    created = api_request(
        test_app,
        "POST",
        "/crawl/jobs",
        json={
            "seeds": ["https://example.com/"],
            "max_pages": 3,
            "max_depth": 1,
        },
    )
    assert created.status_code == 202
    job_id = created.json()["job"]["id"]

    listed = api_request(test_app, "GET", "/crawl/jobs")
    fetched = api_request(test_app, "GET", f"/crawl/jobs/{job_id}")
    cancelled = api_request(test_app, "POST", f"/crawl/jobs/{job_id}/cancel")

    assert listed.status_code == 200
    assert any(job["id"] == job_id for job in listed.json()["jobs"])
    assert fetched.json()["job"]["status"] == "pending"
    assert cancelled.status_code == 200
    assert cancelled.json()["job"]["status"] == "cancelled"


def test_background_worker_crawls_and_indexes_without_live_network(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    job = queue.enqueue(["https://example.com/"], max_pages=1, max_depth=0)
    page = make_page()

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

    processed = asyncio.run(
        process_next_job(
            store,
            queue,
            spider_factory=FakeSpider,
            worker_id="test-worker",
        )
    )

    completed = queue.get_job(job["id"])
    assert processed is True
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["run_id"] is not None
    assert store.search("durable marker")["total_results"] == 1


def test_worker_restart_recovers_unfinished_jobs(tmp_path) -> None:
    store = SearchStore(tmp_path / "search.sqlite3")
    store.initialize()
    queue = CrawlQueue(store.database_path)
    queue.initialize()
    created = queue.enqueue(["https://example.com/"])
    queue.claim_next_job("old-worker")

    queue.initialize()
    recovered = queue.get_job(created["id"])

    assert recovered is not None
    assert recovered["status"] == "pending"
    assert recovered["worker_id"] is None
    assert recovered["lease_expires_at"] is None
    assert recovered["error_message"] == "Worker restarted before the job completed"
