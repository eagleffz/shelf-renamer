from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .abs_client import ABSClient, ABSClientError
from .config import get_settings
from .models import (
    PreviewItem,
    PreviewRequest,
    RenameRequest,
    RenameResponse,
    RenameResult,
)
from .renamer import render_path_template, safe_rename, RenameError

logging.basicConfig(level=get_settings().log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.abs = ABSClient(settings.abs_url, settings.abs_token)
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


def _container_path(abs_path: str, abs_library_root: str) -> str:
    settings = get_settings()
    try:
        rel = os.path.relpath(abs_path, abs_library_root)
    except ValueError:
        rel = abs_path.lstrip("/")
    return os.path.join(settings.media_root, rel)


@app.get("/api/debug/library/{library_id}")
async def debug_library(library_id: str):
    """Return raw ABS metadata for first item — remove after debugging."""
    try:
        r = await _client()._client.get(
            f"/api/libraries/{library_id}/items", params={"limit": 1, "page": 0}
        )
        data = r.json()
        results = data.get("results", [])
        if not results:
            return {"error": "no items"}
        item = results[0]
        return {
            "path": item.get("path"),
            "metadata": item.get("media", {}).get("metadata", {}),
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health")
async def health():
    reachable = await _client().ping()
    return {"status": "ok", "abs_reachable": reachable}


@app.get("/api/config")
async def config():
    return {"default_template": get_settings().default_template}


@app.get("/api/libraries")
async def libraries():
    try:
        return await _client().get_libraries()
    except ABSClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.get("/api/libraries/{library_id}/books")
async def books(library_id: str):
    try:
        return await _client().get_library_items(library_id)
    except ABSClientError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@app.post("/api/preview", response_model=list[PreviewItem])
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


@app.post("/api/rename", response_model=RenameResponse)
async def rename(req: RenameRequest):
    if not req.template.strip():
        raise HTTPException(status_code=422, detail="Template must not be empty")

    # fetch fresh metadata per library
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


# Serve built frontend — must be last
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dist):
    app.mount("/", StaticFiles(directory=_frontend_dist, html=True), name="static")
