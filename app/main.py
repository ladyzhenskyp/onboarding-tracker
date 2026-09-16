"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import blockers, clients, dashboard, exports, pipeline, team

app = FastAPI(title="Client Onboarding Tracker", version="0.2.0")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

app.include_router(dashboard.router)
app.include_router(pipeline.router)
app.include_router(clients.router)
app.include_router(blockers.router)
app.include_router(team.router)
app.include_router(exports.router)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
