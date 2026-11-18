# Local development

## Prerequisites

- Node.js 20.19+ or 22.12+
- Python 3.11+
- A Python SQLite build that includes FTS5 (standard official Python builds normally include it)

## Start the backend

In a terminal:

    cd backend
    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

The database is initialized automatically at `backend/data/apokolips-search.sqlite3`. The `APOKOLIPS_DB_PATH` environment variable can override this location. Startup initializes both the FTS index and the durable job queue, then starts a lightweight background worker.

API health: http://127.0.0.1:8000/health  
Interactive API docs: http://127.0.0.1:8000/docs

## Start the frontend

In a second terminal:

    cd frontend
    npm install
    npm run dev

Open http://127.0.0.1:5173. The default API URL is `http://127.0.0.1:8000`. To change it, create `frontend/.env.local`:

    VITE_API_BASE_URL=http://127.0.0.1:8000

Restart Vite after changing environment variables.

## Queue a crawl

Use the API docs, select `POST /crawl/jobs`, and submit:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

The API responds with HTTP 202 and a job ID. The worker processes the request in the background. Check progress with `GET /crawl/jobs/{job_id}` or recent activity with `GET /crawl/jobs`. Only pending jobs can be cancelled via `POST /crawl/jobs/{job_id}/cancel`.

The queue stores state in SQLite, recovers interrupted jobs after restarts, and retries failed jobs up to three times. A lease expiry is 180 seconds; each crawler execution is bounded to 120 seconds. The direct `POST /crawl` endpoint remains available for synchronous local use.

Only crawl sites you are authorized to crawl. The crawler obeys robots.txt and applies bounded URL counts, timeouts, response sizes, redirects, host delays, and public-address checks.

## Search your local index

Use the web interface or call:

    http://127.0.0.1:8000/search?q=example+website&page=1&page_size=10

All words are combined with AND semantics. Results are ranked using BM25, with stronger weights for title and heading matches. Pagination is limited to 50 results per page.

Additional endpoints:

- `/stats` — index and crawl statistics
- `/crawl/runs` — recent crawl history
- `/crawl/runs/{run_id}` — details of one crawl run

## Run tests and lint

From the backend directory:

    python -m pytest -q
    python -m ruff check app tests

Tests use temporary SQLite files and mocked crawl output. They do not send requests to third-party websites.

## Troubleshooting

- If the frontend says the API cannot be reached, start the backend and check `/health`.
- If the API reports FTS5 unavailable, install a Python distribution linked to an SQLite build with FTS5 enabled.
- If Python cannot import `app`, run Uvicorn from the `backend` directory.
- If a host is skipped, inspect its robots.txt and the crawl issues returned by `POST /crawl`.
- Keep the SQLite database out of Git. Stop the API before making a manual file copy of the database.
