from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .abs_client import ABSClient, ABSClientError
from .auth import init_auth, require_auth, verify_password
from .config import get_settings
from .database import clear_library_history, get_renamed_book_ids, init_db, mark_books_verified, record_rename
from .models import (
    BookMetadata,
    CleanupResponse,
    LoginRequest,
    PreviewItem,
    PreviewRequest,
    RenameRequest,
    RenameResponse,
    RenameResult,
    SeriesUpdateRequest,
    SeriesUpdateResult,
    VerifyRequest,
)
from .renamer import render_path_template, safe_rename, RenameError

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.abs = ABSClient(settings.abs_url, settings.abs_token)
    init_auth()
    await init_db()
    yield
    await app.state.abs.close()


app = FastAPI(title="shelf-renamer", lifespan=lifespan)

settings = get_settings()
if settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )


def _client() -> ABSClient:
    return app.state.abs


def _apply_overrides(book: BookMetadata, overrides: dict | None) -> BookMetadata:
    if not overrides:
        return book
    data = book.model_dump()
    if overrides.get("author"):
        data["authors"] = [{"id": "override", "name": overrides["author"]}]
    for src, dst in [("title", "title"), ("series", "series"), ("narrator", "narrator"), ("year", "published_year")]:
        if src in overrides:
            data[dst] = overrides[src] or None
    if "series_index" in overrides:
        try:
            data["series_index"] = float(overrides["series_index"]) if overrides["series_index"] else None
        except (ValueError, TypeError):
            pass
    return BookMetadata(**data)


def _container_path(abs_path: str, abs_library_root: str) -> str:
    settings = get_settings()
    try:
        rel = os.path.relpath(abs_path, abs_library_root)
    except ValueError:
        rel = abs_path.lstrip("/")
    return os.path.join(settings.media_root, rel)


@app.get("/api/health")
async def health():
    reachable = await _client().ping()
    return {"status": "ok", "abs_reachable": reachable}


@app.get("/api/config")
async def config():
    s = get_settings()
    return {
        "default_template": s.default_template,
        "auth_required": bool(s.app_password),
        "version": s.app_version,
        "abs_url": s.abs_url,
    }


@app.post("/api/auth/login")
async def login(req: LoginRequest):
    token = verify_password(req.password)
    if token is None:
        raise HTTPException(status_code=401, detail="Invalid password")
    return {"token": token}


@app.get("/api/libraries", dependencies=[Depends(require_auth)])
async def libraries():
    try:
        return await _client().get_libraries()
    except ABSClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.get("/api/libraries/{library_id}/books", dependencies=[Depends(require_auth)])
async def books(library_id: str):
    try:
        return await _client().get_library_items(library_id)
    except ABSClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.post("/api/libraries/{library_id}/scan", dependencies=[Depends(require_auth)])
async def scan_library(library_id: str):
    ok = await _client().trigger_scan(library_id)
    if not ok:
        raise HTTPException(status_code=502, detail="ABS scan request failed")
    return {"triggered": True}


@app.get("/api/libraries/{library_id}/history", dependencies=[Depends(require_auth)])
async def history(library_id: str):
    return await get_renamed_book_ids(library_id)


@app.delete("/api/libraries/{library_id}/history", dependencies=[Depends(require_auth)])
async def delete_history(library_id: str):
    cleared = await clear_library_history(library_id)
    return {"cleared": cleared}


@app.post("/api/batch/series", response_model=list[SeriesUpdateResult], dependencies=[Depends(require_auth)])
async def batch_update_series(req: SeriesUpdateRequest):
    results: list[SeriesUpdateResult] = []
    for item in req.items:
        ok = await _client().update_series_index(item.book_id, item.series_id, item.series_name, item.sequence)
        results.append(SeriesUpdateResult(book_id=item.book_id, success=ok))
    return results


@app.post("/api/libraries/{library_id}/verify", dependencies=[Depends(require_auth)])
async def verify_books(library_id: str, req: VerifyRequest):
    entries = [(item.book_id, item.library_id, item.current_path) for item in req.items]
    await mark_books_verified(entries)
    return {"marked": len(entries)}


@app.post("/api/preview", response_model=list[PreviewItem], dependencies=[Depends(require_auth)])
async def preview(req: PreviewRequest):
    if not req.template.strip():
        raise HTTPException(status_code=422, detail="Template must not be empty")
    try:
        books = await _client().get_library_items(req.items[0]["library_id"] if req.items else "")
    except (ABSClientError, IndexError):
        books = []

    book_map = {b.id: b for b in books}
    results: list[PreviewItem] = []
    lib_root = get_settings().media_root

    for item in req.items:
        book = book_map.get(item["book_id"])
        if not book:
            continue
        book = _apply_overrides(book, item.get("overrides"))
        container_path = _container_path(book.abs_path, book.abs_library_root)
        proposed_path = render_path_template(req.template, book, lib_root)
        current_name = os.path.relpath(container_path, lib_root)
        proposed_name = os.path.relpath(proposed_path, lib_root)
        no_change = container_path == proposed_path
        conflict = not no_change and os.path.exists(proposed_path)
        results.append(
            PreviewItem(
                book_id=book.id,
                library_id=book.library_id,
                current_name=current_name,
                proposed_name=proposed_name,
                current_path=container_path,
                proposed_path=proposed_path,
                conflict=conflict,
                no_change=no_change,
            )
        )
    return results


@app.post("/api/rename", response_model=RenameResponse, dependencies=[Depends(require_auth)])
async def rename(req: RenameRequest):
    if not req.template.strip():
        raise HTTPException(status_code=422, detail="Template must not be empty")

    library_ids = {item.library_id for item in req.items}
    books_by_id: dict[str, object] = {}
    for lib_id in library_ids:
        try:
            lib_books = await _client().get_library_items(lib_id)
            for b in lib_books:
                books_by_id[b.id] = b
        except ABSClientError as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail)

    results: list[RenameResult] = []
    renamed_library_ids: set[str] = set()

    for item in req.items:
        book = books_by_id.get(item.book_id)
        if not book:
            results.append(
                RenameResult(
                    book_id=item.book_id,
                    success=False,
                    error="Book not found in ABS",
                    old_path=item.current_path,
                    new_path=item.current_path,
                )
            )
            continue

        book = _apply_overrides(book, item.overrides)
        container_path = _container_path(book.abs_path, book.abs_library_root)
        proposed_path = render_path_template(req.template, book, get_settings().media_root)

        if req.dry_run or container_path == proposed_path:
            results.append(
                RenameResult(
                    book_id=book.id,
                    success=True,
                    old_path=container_path,
                    new_path=proposed_path,
                )
            )
            continue

        try:
            safe_rename(container_path, proposed_path)
            renamed_library_ids.add(item.library_id)
            await record_rename(book.id, item.library_id, container_path, proposed_path)
            results.append(
                RenameResult(
                    book_id=book.id,
                    success=True,
                    old_path=container_path,
                    new_path=proposed_path,
                )
            )
        except RenameError as e:
            results.append(
                RenameResult(
                    book_id=book.id,
                    success=False,
                    error=str(e),
                    old_path=container_path,
                    new_path=proposed_path,
                )
            )

    scan_triggered = False
    if not req.dry_run and renamed_library_ids:
        for lib_id in renamed_library_ids:
            ok = await _client().trigger_scan(lib_id)
            if ok:
                scan_triggered = True

    return RenameResponse(results=results, scan_triggered=scan_triggered)


@app.post("/api/cleanup", response_model=CleanupResponse, dependencies=[Depends(require_auth)])
async def cleanup_empty_dirs():
    root = get_settings().media_root
    removed: list[str] = []
    for dirpath, _dirnames, _filenames in os.walk(root, topdown=False):
        if dirpath == root:
            continue
        try:
            if not os.listdir(dirpath):
                os.rmdir(dirpath)
                removed.append(os.path.relpath(dirpath, root))
        except OSError:
            pass
    return CleanupResponse(removed=removed)


# Serve built frontend — must be last
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")
