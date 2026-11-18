# Apokolips Spider — Phase 02

Apokolips Spider is the first-party discovery and HTML extraction component for Apokolips Search. It does not proxy another search engine and it does not yet write to a persistent index.

## Implemented

- Seed URL crawling and same-run link discovery.
- XML sitemap and robots.txt Sitemap directive discovery.
- robots.txt Allow/Disallow checks before fetching each page or sitemap.
- A descriptive User-Agent identifying this public repository.
- One active request per host and a configurable delay between requests to that host.
- Bounded concurrency, request timeouts, redirect count, response bytes, URL count, page depth, link extraction, and sitemap entries.
- HTTP(S)-only URL normalization; standard ports only; URL credentials rejected.
- DNS resolver rejects a hostname if any resolved address is not globally routable. DNS caching is disabled.
- Redirect targets are revalidated before the next request.
- HTML metadata, title, headings, language, text, canonical URL, and outgoing links are extracted.
- Duplicate canonical URLs and identical page content are reported rather than emitted twice.
- Unit tests run without making live network requests.

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

The API accepts 1–10 seeds, max_pages from 1 to 25, and max_depth from 0 to 3. The lower-level CrawlConfig supports a maximum of 100 URLs for controlled local use.

## Important behaviour

- A robots.txt 404 or 410 is treated as an empty policy. Other unsuccessful responses or network failures fail closed for that host.
- Disallowed URLs are skipped and recorded as crawl issues.
- Only HTML/XHTML pages and XML sitemaps are processed. PDFs, images, archives, feeds, and binary files are not indexed.
- The crawler does not bypass login pages, paywalls, CAPTCHAs, rate limits, or other access restrictions.
- Crawled material is returned by the local API only. It is not persisted and is not yet searchable.
- Run only against sites you are authorized to crawl and comply with each publisher's terms and applicable law.

## Next phase

Phase 03 will add durable crawl-state storage, a queue/scheduler, and a first-party search index. Search results must not be shown until the content has been indexed and quality checks have passed.
