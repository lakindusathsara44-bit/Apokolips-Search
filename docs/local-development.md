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

The database is initialized automatically at `backend/data/apokolips-search.sqlite3`. The `APOKOLIPS_DB_PATH` environment variable can override this location. Startup initializes the FTS index, durable crawl queue, API-key tables, and one lightweight background worker.

API health: http://127.0.0.1:8000/health  
Interactive API documentation: http://127.0.0.1:8000/docs

## Start the frontend

In a second terminal:

    cd frontend
    npm install
    npm run dev

Open http://127.0.0.1:5173. The default API URL is `http://127.0.0.1:8000`. To change it, create `frontend/.env.local`:

    VITE_API_BASE_URL=http://127.0.0.1:8000

Restart Vite after changing environment variables.

## Enable public API mode locally

Public mode deliberately requires an administrator secret. In Windows PowerShell, generate a high-entropy token and set the environment variables in the same terminal used to start Uvicorn:

    $env:APOKOLIPS_PUBLIC_MODE = "true"
    $env:APOKOLIPS_ADMIN_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(48))"
    $env:APOKOLIPS_CORS_ORIGINS = "https://apokolips.xyz,https://www.apokolips.xyz"
    uvicorn app.main:app --host 127.0.0.1 --port 8000

Keep the generated administrator token private. The API refuses public-mode startup if the token is missing or shorter than 32 characters. CORS origins are exact comma-separated origins; wildcard entries are ignored.

Create a developer key using Swagger UI at `/docs`, endpoint `POST /admin/api-keys`, with the header `Authorization: Bearer YOUR_ADMIN_TOKEN` and JSON body:

    {
      "name": "My test application",
      "requests_per_minute": 60
    }

Copy the returned `api_key` immediately. It is returned once; only its SHA-256 hash is stored. Never put the key in frontend JavaScript or Git. Use it in the `X-API-Key` header for `GET /api/v1/search?q=...`.

Public mode disables the old unauthenticated `/search` endpoint and protects crawler controls, crawl job/history endpoints, and operational statistics with the administrator token. Key creation/listing/revocation always requires the administrator token.

## Queue a crawl (local mode)

Use the API docs, select `POST /crawl/jobs`, and submit:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

The API responds with HTTP 202 and a job ID. The worker processes it in the background. Check progress with `GET /crawl/jobs/{job_id}` or `GET /crawl/jobs`. Only pending jobs can be cancelled. The queue recovers interrupted jobs after restarts and retries failures up to three times. The worker lease is 180 seconds; each crawler execution is bounded to 120 seconds.

Only crawl sites you are authorized to crawl. The crawler obeys robots.txt and applies bounded URL counts, timeouts, response sizes, redirects, host delays, and public-address checks.

## Search the local index

Local development mode:

    http://127.0.0.1:8000/search?q=example+website&page=1&page_size=10

Public API mode (replace the key with the one-time secret created by the administrator):

    curl --get http://127.0.0.1:8000/api/v1/search -H "X-API-Key: aps_live_your_key" --data-urlencode "q=example website"

The public API supports page sizes up to 20. Search terms use AND semantics and results are ranked with BM25. Public API keys have an independent fixed UTC-minute quota, default 60 requests/minute. HTTP 429 responses include `Retry-After` and rate-limit headers.

See [Public API v1](public-api.md) for endpoint schemas, key management, response examples, error codes, and the deployment checklist.

## Run tests and lint

From the backend directory:

    python -m pytest -q
    python -m ruff check app tests

Tests use temporary SQLite files and mocked crawler output. They do not send requests to third-party websites.

## Troubleshooting

- If the frontend cannot reach the API, start the backend and check `/health`.
- If FTS5 is unavailable, install a Python distribution linked to SQLite with FTS5 enabled.
- If Python cannot import `app`, run Uvicorn from the `backend` directory.
- If a host is skipped, inspect its robots.txt and crawl issue records.
- Keep the SQLite database out of Git. Stop the API before manually copying its database file.
