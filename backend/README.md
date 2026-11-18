# Backend

Local FastAPI API, Apokolips Spider crawler, SQLite metadata store, and first-party FTS5 search engine.

## Run

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health check: http://127.0.0.1:8000/health
Interactive API docs: http://127.0.0.1:8000/docs

The local SQLite database is created automatically at \`backend/data/apokolips-search.sqlite3\`. Override its location with \`APOKOLIPS_DB_PATH\`.

## Main API endpoints

- \`POST /crawl\` — crawl permitted seed URLs, persist crawl metadata and extracted pages, and update the search index.
- \`GET /search?q=...\` — search Apokolips' own FTS5 index using BM25 relevance ranking.
- \`GET /stats\` — return indexed document and crawl-run counts.
- \`GET /crawl/runs\` — list recent crawl runs.
- \`GET /crawl/runs/{run_id}\` — inspect one crawl run.
- \`GET /health\` — check database and FTS5 availability.

Example crawl request:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

Example search request:

    http://127.0.0.1:8000/search?q=example+website&page=1&page_size=10

Search combines all supplied words (AND semantics). Title matches have a higher BM25 weight than description, headings, and body text. Search results always come from the local Apokolips index; the API does not proxy another search engine.

## Run tests and lint

    python -m pytest -q
    python -m ruff check app tests

The test suite uses temporary databases and mocked crawler output; it does not initiate live external crawls.

## Storage and backup

Stop the API before copying the database file. SQLite WAL may use companion \`-wal\` and \`-shm\` files while the API is running. Keep \`backend/data/\` out of Git and back up the database according to the importance of the indexed content.

See \`../crawler/README.md\` and \`../docs/local-development.md\` for crawler policy and local setup.
