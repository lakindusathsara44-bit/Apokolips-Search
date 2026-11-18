# Local development

## Prerequisites

- Node.js 20.19+ or 22.12+
- Python 3.11+

## Start the frontend

    cd frontend
    npm install
    npm run dev

Open http://127.0.0.1:5173.

## Start the API

In a second terminal:

    cd backend
    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health endpoint: http://127.0.0.1:8000/health
Interactive API docs: http://127.0.0.1:8000/docs

## Run crawler tests

From the backend directory:

    python -m pytest -q
    python -m ruff check app tests

## Try Apokolips Spider

Open http://127.0.0.1:8000/docs, expand POST /crawl, and use a small request:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

The API is capped at 25 URLs per request. It checks robots.txt, restricts connections to public IP addresses, uses per-host throttling, and limits redirects, bytes, concurrency, and elapsed request time. Use only public sites you are authorized to crawl.

## Current limitations

Phase 02 extracts HTML and returns it from the local API. It does not yet save crawl data, build an index, or return search results. The frontend search box remains a foundation preview until a first-party index and search API are implemented.

## Troubleshooting

- If port 5173 is busy, stop the other Vite process before restarting.
- If Python cannot import app, run Uvicorn from the backend directory.
- If a host is skipped, inspect its robots.txt and the issues array returned by POST /crawl.
- Use a supported Node.js LTS release if dependency installation fails.
