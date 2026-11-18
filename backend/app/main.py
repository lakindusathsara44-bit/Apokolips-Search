from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Apokolips Search API",
    version="0.1.0",
    description="Local foundation API for the independent Apokolips Search engine.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "apokolips-search-api", "version": "0.1.0"}


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"message": "Apokolips Search API", "docs": "/docs"}