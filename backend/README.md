# Backend

Local FastAPI foundation.

## Run

    python -m venv .venv
    # Windows PowerShell: .venv\Scripts\Activate.ps1
    # macOS/Linux: source .venv/bin/activate
    pip install -r requirements.txt
    uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Health check: http://127.0.0.1:8000/health
API docs: http://127.0.0.1:8000/docs