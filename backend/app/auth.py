from __future__ import annotations

import secrets

from fastapi import Header, HTTPException

from .config import get_settings

_session_token: str | None = None


def init_auth() -> None:
    global _session_token
    if get_settings().app_password:
        _session_token = secrets.token_hex(32)


def verify_password(password: str) -> str | None:
    settings = get_settings()
    if not settings.app_password:
        return ""
    if password == settings.app_password:
        return _session_token
    return None


def require_auth(authorization: str = Header(default="")) -> None:
    if not get_settings().app_password:
        return
    token = authorization.removeprefix("Bearer ").strip()
    if not _session_token or token != _session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")
