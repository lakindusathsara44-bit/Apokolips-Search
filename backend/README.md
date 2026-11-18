# Backend

Local FastAPI API, Apokolips Spider crawler, SQLite metadata store and durable queue, background worker, and first-party FTS5 search engine.

## Run

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health check: http://127.0.0.1:8000/health  
Interactive API docs: http://127.0.0.1:8000/docs

The local SQLite database is created automatically at `backend/data/apokolips-search.sqlite3`. Override its location with `APOKOLIPS_DB_PATH`.

## Main API endpoints

- `POST /crawl` — run a bounded crawl immediately, persist its metadata/pages, and update the index.
- `POST /crawl/jobs` — queue a crawl for background execution (HTTP 202).
- `GET /crawl/jobs` — list recent queued/running/completed/failed jobs.
- `GET /crawl/jobs/{job_id}` — inspect one job, including retry and crawl-run metadata.
- `POST /crawl/jobs/{job_id}/cancel` — cancel a job only while it is pending.
- `GET /search?q=...` — search Apokolips' own FTS5 index using BM25 ranking.
- `GET /stats` — return indexed document and crawl-run counts.
- `GET /crawl/runs` — list recent crawl runs.
- `GET /crawl/runs/{run_id}` — inspect one crawl run.
- `GET /health` — check database and FTS5 availability.

Example background job request:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

Example response (abbreviated):

    {
      "job": {
        "id": "…",
        "status": "pending",
        "attempts": 0,
        "seeds": ["https://www.example.com/"]
      }
    }

The application starts one lightweight worker in its FastAPI lifespan. The worker claims jobs using a SQLite write transaction, stores a crawl-run record, crawls and indexes permitted pages, then marks the job completed. Failed attempts are retried up to three times with short exponential backoff. A 180-second lease allows a restarted application to recover jobs left running by a stopped worker. Pending jobs can be cancelled; running jobs cannot be cancelled via the API.

The queue is local and single-process. It is not a distributed queue or a recurring schedule service. Bind the API to localhost; do not expose the unauthenticated crawl endpoints publicly.

## Search and storage

Search combines all supplied words (AND semantics). Title matches have a higher BM25 weight than description, headings, and body text. Search results always come from the local Apokolips index; the API does not proxy another search engine.

Stop the API before copying the database file. SQLite WAL may use companion `-wal` and `-shm` files while the API is running. Keep `backend/data/` out of Git and back up the database according to the importance of the indexed content.

## Run tests and lint

    python -m pytest -q
    python -m ruff check app tests

The test suite uses temporary databases and mocked crawler output; it does not initiate live external crawls.

See `../crawler/README.md` and `../docs/local-development.md` for crawler policy and local setup.
