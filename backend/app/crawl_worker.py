"""Single-process background runner for durable crawl jobs."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable

from .crawl_queue import CrawlQueue
from .crawler import ApokolipsSpider, CrawlConfig
from .search_store import SearchStore

logger = logging.getLogger(__name__)

CRAWL_TIMEOUT_SECONDS = 120
JOB_LEASE_SECONDS = 180


async def process_next_job(
    store: SearchStore,
    queue: CrawlQueue,
    spider_factory: Callable[[CrawlConfig], ApokolipsSpider] = ApokolipsSpider,
    worker_id: str = "apokolips-spider-test-worker",
) -> bool:
    """Claim and process one job. Returns False when the queue is empty."""
    job = await asyncio.to_thread(
        queue.claim_next_job,
        worker_id,
        JOB_LEASE_SECONDS,
    )
    if job is None:
        return False

    job_id = job["id"]
    run_id: str | None = None
    try:
        run_id = await asyncio.to_thread(store.create_crawl_run, job["seeds"])
        attached = await asyncio.to_thread(queue.attach_run, job_id, worker_id, run_id)
        if not attached:
            await asyncio.to_thread(
                store.fail_crawl_run,
                run_id,
                "The crawl job lease was lost before the crawl started",
            )
            return True

        spider = spider_factory(
            CrawlConfig(
                max_pages=job["max_pages"],
                max_depth=job["max_depth"],
            )
        )
        report = await asyncio.wait_for(
            spider.crawl(job["seeds"]),
            timeout=CRAWL_TIMEOUT_SECONDS,
        )
        await asyncio.to_thread(store.save_crawl_result, run_id, report)
        completed = await asyncio.to_thread(queue.complete, job_id, worker_id)
        if not completed:
            logger.warning("Crawl job %s completed after its worker lease was lost", job_id)
    except TimeoutError:
        message = f"Crawl exceeded the {CRAWL_TIMEOUT_SECONDS}-second job limit"
        if run_id is not None:
            await asyncio.to_thread(store.fail_crawl_run, run_id, message)
        retry_delay = min(60, 2 ** job["attempts"])
        await asyncio.to_thread(
            queue.fail,
            job_id,
            worker_id,
            message,
            retry_delay,
        )
        logger.warning("Crawl job %s timed out", job_id)
    except Exception:
        message = "The crawl or persistence operation failed; inspect the crawl run record"
        if run_id is not None:
            await asyncio.to_thread(store.fail_crawl_run, run_id, message)
        retry_delay = min(60, 2 ** job["attempts"])
        await asyncio.to_thread(
            queue.fail,
            job_id,
            worker_id,
            message,
            retry_delay,
        )
        logger.exception("Crawl job %s failed", job_id)
    return True


async def run_crawl_worker(
    store: SearchStore,
    queue: CrawlQueue,
    poll_interval_seconds: float = 1.0,
) -> None:
    """Poll continuously with one lightweight worker per API process."""
    worker_id = f"apokolips-spider-{uuid.uuid4().hex}"
    while True:
        processed = await process_next_job(store, queue, worker_id=worker_id)
        if not processed:
            await asyncio.sleep(poll_interval_seconds)
