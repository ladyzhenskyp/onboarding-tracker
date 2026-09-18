"""Demo login: one shared account, a signed session cookie, nothing else.

This is deliberately minimal. The point is that a public demo can't be edited
anonymously — not to demonstrate an auth system. A real deployment would use
per-user accounts, hashed passwords and an identity provider (SSO).

How it works
- POST /login checks the form against DEMO_USERNAME / DEMO_PASSWORD from settings.
- On success we set a cookie whose value is signed with SECRET_KEY (itsdangerous),
  so it can't be forged; it carries the username and nothing secret.
- `AuthMiddleware` runs before every request: if the cookie is missing or invalid
  and the path isn't public, redirect to /login (HTMX callers get a header that
  tells HTMX to do a full-page redirect instead of swapping HTML).
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response
from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.deps import templates

COOKIE_NAME = "tracker_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 14  # two weeks
PUBLIC_PATHS = ("/login", "/logout", "/healthz", "/static")

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="tracker-session")


def _sign(username: str) -> str:
    return _serializer.dumps({"u": username})


def current_user(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=SESSION_MAX_AGE)["u"]
    except (BadSignature, KeyError, TypeError):
        return None


def _credentials_ok(username: str, password: str) -> bool:
    # compare_digest avoids leaking which field was wrong via timing
    return hmac.compare_digest(username, settings.demo_username) and hmac.compare_digest(
        password, settings.demo_password
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path.startswith(PUBLIC_PATHS) or current_user(request):
            return await call_next(request)
        if request.headers.get("HX-Request") == "true":
            # Tell HTMX to navigate rather than swap the login page into a fragment.
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        nxt = request.url.path
        return RedirectResponse(url=f"/login?next={nxt}", status_code=303)


router = APIRouter(tags=["auth"])


@router.get("/login", name="login")
def login_form(request: Request):
    if current_user(request):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "now": None,
            "error": None,
            "next": request.query_params.get("next", "/"),
            "demo_username": settings.demo_username,
            "demo_password": settings.demo_password,
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
):
    if not _credentials_ok(username.strip(), password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "now": None,
                "error": "That username and password don't match.",
                "next": next,
                "demo_username": settings.demo_username,
                "demo_password": settings.demo_password,
            },
            status_code=401,
        )
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    resp = RedirectResponse(url=target, status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        _sign(username.strip()),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return resp


@router.post("/logout", name="logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp
