"""FastAPI application entry point.

Run locally:  uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.auth import AuthMiddleware
from app.auth import router as auth_router
from app.deps import templates
from app.models import utcnow
from app.routers import (
    blockers,
    calendar,
    clients,
    dashboard,
    exports,
    insights,
    pipeline,
    search,
    team,
)
from app.services import demo_reset


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Start the nightly demo reset with the app, and stop it cleanly on shutdown."""
    task = demo_reset.start()
    yield
    if task:
        task.cancel()


app = FastAPI(title="Client Onboarding Tracker", version="0.3.0", lifespan=lifespan)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.add_middleware(AuthMiddleware)

app.include_router(auth_router)

app.include_router(dashboard.router)
app.include_router(pipeline.router)
app.include_router(clients.router)
app.include_router(blockers.router)
app.include_router(calendar.router)
app.include_router(team.router)
app.include_router(insights.router)
app.include_router(search.router)
app.include_router(exports.router)


@app.exception_handler(StarletteHTTPException)
async def friendly_not_found(request: Request, exc: StarletteHTTPException):
    """A person who follows a link to something that no longer exists (often because the demo
    data was just reset) gets a page that says so, not raw JSON. HTMX and API callers keep
    the plain response; app.js turns their 404 into a toast."""
    wants_page = "text/html" in request.headers.get("accept", "")
    if exc.status_code == 404 and wants_page and request.headers.get("HX-Request") != "true":
        return templates.TemplateResponse(
            request, "not_found.html", {"now": utcnow()}, status_code=404
        )
    return await http_exception_handler(request, exc)


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict[str, str]:
    return {"status": "ok"}
