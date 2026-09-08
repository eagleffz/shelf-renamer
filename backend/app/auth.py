from __future__ import annotations

import secrets
import time
from collections import deque

from fastapi import HTTPException, Request

from .config import get_settings

COOKIE = "shelf-renamer-session"
SESSION_SECONDS = 12 * 60 * 60
_sessions: dict[str, float] = {}
_attempts: dict[str, deque] = {}


def init_auth() -> None:
    _sessions.clear()
    _attempts.clear()


def _constant_time_eq(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_password(password: str, client: str = "local") -> str | None:
    now = time.monotonic()
    for key in list(_attempts):
        if not _attempts[key] or _attempts[key][-1] <= now - 60:
            del _attempts[key]
    attempts = _attempts.setdefault(client, deque())
    while attempts and attempts[0] <= now - 60:
        attempts.popleft()
    if len(attempts) >= 5 or sum(map(len, _attempts.values())) >= 100:
        raise HTTPException(
            429,
            "Too many login attempts. Try again in one minute.",
            headers={"Retry-After": "60"},
        )
    attempts.append(now)
    if not _constant_time_eq(password, get_settings().app_password):
        return None
    for token, expiry in list(_sessions.items()):
        if expiry <= now:
            del _sessions[token]
    if len(_sessions) >= 1000:
        raise HTTPException(429, "Too many active sessions")
    token = secrets.token_urlsafe(32)
    _sessions[token] = now + SESSION_SECONDS
    return token


def request_token(request: Request) -> str:
    return (
        request.cookies.get(COOKIE, "")
        or request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    )


def revoke_session(request: Request) -> None:
    _sessions.pop(request_token(request), None)


def require_auth(request: Request) -> None:
    if not get_settings().app_password:
        return
    token = request_token(request)
    if _sessions.get(token, 0) <= time.monotonic():
        _sessions.pop(token, None)
        raise HTTPException(401, "Session expired. Please sign in again.")
