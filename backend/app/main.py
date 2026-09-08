from __future__ import annotations

import asyncio
import fcntl
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .abs_client import ABSClient, ABSClientError
from .auth import (
    COOKIE,
    SESSION_SECONDS,
    init_auth,
    require_auth,
    revoke_session,
    verify_password,
)
from .config import get_settings
from .database import (
    begin_operation,
    clear_library_history,
    finish_operation,
    get_renamed_book_ids,
    init_db,
    operation_history,
)
from .models import (
    LoginRequest,
    PreviewItem,
    PreviewRequest,
    RenameRequest,
    RenameResponse,
    RenameResult,
    SeriesUpdateRequest,
    SeriesUpdateResult,
)
from .planner import _resolve_paths, _sorted_volume_map, build_plan, matches_plan
from .renamer import RenameError, safe_rename, validate_path

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.abs = ABSClient(settings.abs_url, settings.abs_token)
    app.state.mutation_lock = asyncio.Lock()
    init_auth()
    await init_db()
    yield
    await app.state.abs.close()


app = FastAPI(title="shelf-renamer", lifespan=lifespan)
if get_settings().debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )


@app.middleware("http")
async def same_origin_mutations(request: Request, call_next):
    # SameSite cookies plus Origin checks protect cookie-authenticated writes.
    origin = request.headers.get("origin")
    allowed = {str(request.base_url).rstrip("/")}
    if get_settings().debug:
        allowed.add("http://localhost:5173")
    if (
        request.method not in {"GET", "HEAD", "OPTIONS"}
        and origin
        and origin not in allowed
    ):
        return Response("Cross-origin writes are not allowed", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _client() -> ABSClient:
    return app.state.abs


@asynccontextmanager
async def mutation_lock():
    async with app.state.mutation_lock:
        # Coordinates rename, metadata updates, and cleanup across processes too.
        with await asyncio.to_thread(
            open, get_settings().db_path + ".lock", "a"
        ) as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise HTTPException(
                    409, "Another operation is running. Please retry shortly."
                )
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)


@app.get("/api/live")
async def live():
    return {"status": "ok"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "abs_reachable": await _client().ping()}


@app.get("/api/config")
async def config():
    s = get_settings()
    return {
        "default_template": s.default_template,
        "auth_required": bool(s.app_password),
        "version": s.app_version,
        "abs_url": s.abs_url,
        "media_root": s.media_root,
        "volume_map": [
            {"abs_root": a, "container_root": c} for a, c in s.parsed_volume_map()
        ],
    }


@app.post("/api/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    token = verify_password(
        req.password, request.client.host if request.client else "unknown"
    )
    if token is None:
        raise HTTPException(401, "Invalid password")
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=SESSION_SECONDS,
    )
    return {"authenticated": True}


@app.get("/api/auth/session", dependencies=[Depends(require_auth)])
async def session():
    return {"authenticated": True}


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    revoke_session(request)
    response.delete_cookie(COOKIE)
    return {"authenticated": False}


@app.get("/api/libraries", dependencies=[Depends(require_auth)])
async def libraries():
    try:
        return await _client().get_libraries()
    except ABSClientError as e:
        raise HTTPException(e.status_code if e.status_code != 401 else 502, e.detail)


@app.get("/api/libraries/{library_id}/books", dependencies=[Depends(require_auth)])
async def books(library_id: str, refresh: bool = False):
    try:
        return await _client().get_library_items(library_id, use_cache=not refresh)
    except ABSClientError as e:
        raise HTTPException(e.status_code if e.status_code != 401 else 502, e.detail)


@app.post("/api/libraries/{library_id}/scan", dependencies=[Depends(require_auth)])
async def scan_library(library_id: str):
    if not await _client().trigger_scan(library_id):
        raise HTTPException(
            502, "ABS scan request failed. Check the ABS connection and token."
        )
    return {"triggered": True}


@app.get("/api/libraries/{library_id}/history", dependencies=[Depends(require_auth)])
async def history(library_id: str):
    return await get_renamed_book_ids(library_id)


@app.get("/api/libraries/{library_id}/operations", dependencies=[Depends(require_auth)])
async def operations(library_id: str):
    return await operation_history(library_id)


@app.delete("/api/libraries/{library_id}/history", dependencies=[Depends(require_auth)])
async def delete_history(library_id: str):
    return {"cleared": await clear_library_history(library_id)}


@app.post(
    "/api/batch/series",
    response_model=list[SeriesUpdateResult],
    dependencies=[Depends(require_auth)],
)
async def batch_update_series(req: SeriesUpdateRequest):
    sem = asyncio.Semaphore(8)

    async def one(item):
        async with sem:
            try:
                ok = await _client().update_series_index(
                    item.book_id, item.series_id, item.series_name, item.sequence
                )
                return SeriesUpdateResult(
                    book_id=item.book_id,
                    success=ok,
                    error=None if ok else "ABS rejected this update",
                )
            except ABSClientError as e:
                return SeriesUpdateResult(
                    book_id=item.book_id, success=False, error=e.detail
                )

    async with mutation_lock():
        return list(await asyncio.gather(*(one(item) for item in req.items)))


@app.post(
    "/api/preview",
    response_model=list[PreviewItem],
    dependencies=[Depends(require_auth)],
)
async def preview(req: PreviewRequest):
    try:
        return await build_plan(_client(), req.template, req.items)
    except RenameError as e:
        raise HTTPException(422, str(e))


@app.post(
    "/api/rename", response_model=RenameResponse, dependencies=[Depends(require_auth)]
)
async def rename(req: RenameRequest):
    async with mutation_lock():
        try:
            plan = await build_plan(_client(), req.template, req.items, fresh=True)
        except RenameError as e:
            raise HTTPException(422, str(e))
        for item, planned in zip(req.items, plan):
            if planned.conflict:
                raise HTTPException(409, f"Preview again: {planned.error}")
            if not req.dry_run and (
                item.current_path != planned.current_path
                or not matches_plan(item.preview_token, planned.preview_token)
            ):
                raise HTTPException(
                    409,
                    "The preview expired or the book, template, or path changed. Preview again before renaming.",
                )

        results, changed, scan_errors = [], set(), []
        for item, planned in zip(req.items, plan):
            result = RenameResult(
                book_id=item.book_id,
                success=False,
                old_path=planned.current_path,
                new_path=planned.proposed_path,
            )
            if req.dry_run or planned.no_change:
                result.success = True
                results.append(result)
                continue
            operation_id = None
            try:
                # Commit intent before touching disk. A crash leaves a visible
                # pending operation for manual reconciliation, never a blind retry.
                operation_id = await begin_operation(
                    item.book_id,
                    item.library_id,
                    planned.current_path,
                    planned.proposed_path,
                )
                # Use the longest mapped root that contains this validated path.
                roots = [os.path.realpath(c) for _, c in _sorted_volume_map()] or [
                    os.path.realpath(get_settings().media_root)
                ]
                root = max(
                    (
                        r
                        for r in roots
                        if planned.current_path.startswith(r + os.sep)
                        and planned.proposed_path.startswith(r + os.sep)
                    ),
                    key=len,
                )
                await asyncio.to_thread(
                    safe_rename, planned.current_path, planned.proposed_path, root
                )
                result.success = True
                changed.add(item.library_id)
                await finish_operation(operation_id, True)
            except Exception as e:
                logger.exception("Rename operation failed for %s", item.book_id)
                result.error = (
                    f"Moved, but could not finish history: {e}"
                    if result.success
                    else str(e)
                )
                if operation_id is not None and not result.success:
                    try:
                        await finish_operation(operation_id, False, str(e))
                    except Exception:
                        logger.exception(
                            "Could not record failed operation %s", operation_id
                        )
            results.append(result)

        scanned = False
        for library_id in changed:
            if await _client().trigger_scan(library_id):
                scanned = True
            else:
                scan_errors.append(library_id)
        return RenameResponse(
            results=results, scan_triggered=scanned, scan_errors=scan_errors
        )


class CleanupRequest(BaseModel):
    library_id: str
    dry_run: bool = True
    paths: list[str] = []


def _empty_dirs(roots: list[str]) -> list[str]:
    empty = set()
    for root in roots:
        for path, dirs, files in os.walk(root, topdown=False, followlinks=False):
            if path == root or os.path.islink(path):
                continue
            if not files and all(os.path.join(path, d) in empty for d in dirs):
                empty.add(path)
    return sorted(empty, key=lambda p: (-p.count(os.sep), p))


@app.post("/api/cleanup", dependencies=[Depends(require_auth)])
async def cleanup(req: CleanupRequest):
    try:
        libraries = await _client().get_libraries()
        library = next((lib for lib in libraries if lib.id == req.library_id), None)
        if not library:
            raise HTTPException(404, "Library not found")
        roots = list(
            {
                _resolve_paths(root.rstrip("/") + "/.cleanup-check", root)[1]
                for root in library.folders
            }
        )
    except (ABSClientError, RenameError) as e:
        raise HTTPException(422, str(e))
    async with mutation_lock():
        candidates = await asyncio.to_thread(_empty_dirs, roots)
        if req.dry_run:
            return {"removed": [], "candidates": candidates, "errors": []}
        if not set(req.paths).issubset(candidates):
            raise HTTPException(409, "Folders changed. Preview cleanup again.")

        def remove():
            removed, errors = [], []
            for path in candidates:
                if path not in req.paths:
                    continue
                try:
                    root = max(
                        (root for root in roots if path.startswith(root + os.sep)),
                        key=len,
                    )
                    validate_path(path, root)
                    from .renamer import _parent_fd

                    with _parent_fd(root, path) as parent:
                        os.rmdir(os.path.basename(path), dir_fd=parent)
                    removed.append(path)
                except (OSError, RenameError) as e:
                    errors.append(f"{path}: {e}")
            return {"removed": removed, "candidates": [], "errors": errors}

        return await asyncio.to_thread(remove)


_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")
