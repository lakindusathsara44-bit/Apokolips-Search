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
    pip install -r requirements.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health endpoint: http://127.0.0.1:8000/health
Interactive API docs: http://127.0.0.1:8000/docs

## Current limitations

The search interface is a foundation preview. No crawler, persistent index, or live search endpoint is implemented in Phase 01. Search submission displays an honest not-yet-connected message rather than fabricated results.

## Troubleshooting

- If port 5173 is busy, stop the other Vite process before restarting.
- If Python cannot import app, run Uvicorn from the backend directory.
- Use a supported Node.js LTS release if dependency installation fails.