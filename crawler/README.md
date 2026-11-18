# Apokolips Spider

Apokolips Spider is the first-party discovery and HTML extraction component for Apokolips Search. It does not proxy another search engine.

## Implemented

- Seed URL crawling and same-run link discovery.
- XML sitemap and robots.txt Sitemap directive discovery.
- robots.txt Allow/Disallow matching with longest-path precedence and Allow tie-breaking.
- A descriptive User-Agent identifying this public repository.
- Fail-closed behaviour when robots.txt cannot be checked.
- One active request per host and a configurable delay between requests to that host.
- Bounded concurrency, request timeouts, redirect count, response bytes, URL count, page depth, link extraction, and sitemap entries.
- HTTP(S)-only URL normalization; standard ports only; URL credentials rejected.
- DNS resolver rejects a hostname if any resolved address is not globally routable. DNS caching is disabled.
- Redirect targets are revalidated before the next request.
- HTML title, description, headings, language, text, canonical URL, and outgoing links are extracted.
- Duplicate canonical URLs and identical page content are reported rather than emitted twice.
- Offline unit tests; automated tests do not send requests to live websites.

## Persistence and indexing

Phase 03 connects the crawler to the local SearchStore. The POST /crawl API creates a crawl-run record, stores per-URL outcomes, upserts documents by canonical URL, and updates the SQLite FTS5 index in the same database transaction. Pages that are recrawled update the existing canonical document rather than creating another search result.

Crawl history is available through GET /crawl/runs and GET /crawl/runs/{run_id}. The database is stored under backend/data by default; APOKOLIPS_DB_PATH can override its location.

## Start locally

From the backend directory:

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Open http://127.0.0.1:8000/docs and use POST /crawl.

Example request body:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

The API accepts 1–10 seeds, max_pages from 1 to 25, and max_depth from 0 to 3.

## Important behaviour

- A robots.txt 404 or 410 is treated as an empty policy. Other unsuccessful responses or network failures fail closed for that host.
- Disallowed URLs are skipped and recorded as crawl issues.
- Only HTML/XHTML pages and XML sitemaps are processed. PDFs, images, archives, feeds, and binary files are not indexed.
- The crawler does not bypass login pages, paywalls, CAPTCHAs, rate limits, or other access restrictions.
- Crawl execution is request-driven, bounded, and local. There is not yet a continuous background scheduler or worker queue.
- The local index contains only pages that have actually been crawled and stored. It is not a copy of the entire web.
- Run only against sites you are authorized to crawl and comply with each publisher's terms and applicable law.

## Planned work

A durable background queue, scheduler, multi-worker operation, and broader index quality pipeline remain future work.
