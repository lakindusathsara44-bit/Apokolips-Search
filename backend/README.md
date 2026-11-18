# Backend

Local FastAPI API and Apokolips Spider crawler.

## Run

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    python -m pip install -r requirements-dev.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health check: http://127.0.0.1:8000/health
API docs: http://127.0.0.1:8000/docs

## Run crawler tests

    python -m pytest -q
    python -m ruff check app tests

## Crawl endpoint

POST /crawl accepts JSON with 1–10 seed URLs, max_pages (1–25), and max_depth (0–3). Example:

    {
      "seeds": ["https://www.example.com/"],
      "max_pages": 5,
      "max_depth": 1
    }

The endpoint returns extracted page metadata/text and crawl issues. It does not store the data; persistence and a searchable index are Phase 03 work. See ../crawler/README.md for safeguards and limits.
