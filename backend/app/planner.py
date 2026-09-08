"""Build and sign reviewable rename plans without mutating the library."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
import unicodedata
from functools import lru_cache

from .abs_client import ABSClientError
from .config import get_settings
from .models import BookMetadata, PreviewItem, PreviewSelection
from .renamer import (
    RenameError,
    _build_variables,
    render_path_template,
    validate_path,
    validate_template,
)

_secret = secrets.token_bytes(32)


@lru_cache
def _sorted_volume_map() -> tuple[tuple[str, str], ...]:
    return tuple(
        sorted(
            get_settings().parsed_volume_map(), key=lambda x: len(x[0]), reverse=True
        )
    )


def _resolve_paths(abs_path: str, abs_library_root: str) -> tuple[str, str]:
    path = os.path.normpath(abs_path)
    library = os.path.normpath(abs_library_root)
    if (
        not os.path.isabs(path)
        or not os.path.isabs(library)
        or os.path.commonpath([path, library]) != library
    ):
        raise RenameError("ABS path does not belong to its reported library folder")
    for abs_root, container_root in _sorted_volume_map():
        if path == abs_root or path.startswith(abs_root.rstrip("/") + "/"):
            # A broad mount may contain multiple libraries; stay inside this library.
            root = (
                os.path.realpath(
                    os.path.join(container_root, os.path.relpath(library, abs_root))
                )
                if library.startswith(abs_root.rstrip("/") + "/")
                else os.path.realpath(container_root)
            )
            mapped = os.path.join(
                os.path.realpath(container_root), os.path.relpath(path, abs_root)
            )
            return validate_path(mapped, root), root
    if _sorted_volume_map():
        raise RenameError(
            "No volume mapping matches this library. Add an explicit VOLUME_MAP entry."
        )
    root = os.path.realpath(get_settings().media_root)
    return validate_path(os.path.join(root, os.path.relpath(path, library)), root), root


def _apply_overrides(book: BookMetadata, overrides: dict[str, str]) -> BookMetadata:
    data = book.model_dump()
    if "author" in overrides:
        data["authors"] = (
            [{"id": "override", "name": overrides["author"]}]
            if overrides["author"]
            else []
        )
    for src, dst in [
        ("title", "title"),
        ("series", "series"),
        ("narrator", "narrator"),
        ("year", "published_year"),
    ]:
        if src in overrides:
            data[dst] = overrides[src] or None
    if "series_index" in overrides:
        data["series_index"] = (
            float(overrides["series_index"]) if overrides["series_index"] else None
        )
    return BookMetadata(**data)


def fingerprint(
    template: str,
    item: PreviewSelection,
    book: BookMetadata,
    current: str,
    proposed: str,
) -> str:
    st = os.lstat(current)
    payload = [
        template,
        item.model_dump(include={"book_id", "library_id", "overrides"}),
        book.model_dump(),
        current,
        proposed,
        [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns],
    ]
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def sign_plan(fingerprint_value: str, expiry: int | None = None) -> str:
    expiry = expiry or int(time.time()) + 1800
    payload = f"{expiry}:{fingerprint_value}"
    return (
        f"{payload}:{hmac.new(_secret, payload.encode(), hashlib.sha256).hexdigest()}"
    )


def matches_plan(token: str, fresh_token: str) -> bool:
    try:
        expiry, value, _signature = token.split(":")
        return (
            int(expiry) > time.time()
            and hmac.compare_digest(token, sign_plan(value, int(expiry)))
            and hmac.compare_digest(value, fresh_token.split(":")[1])
        )
    except (ValueError, IndexError):
        return False


def _render(
    template: str, items: list[PreviewSelection], book_map: dict, failures: dict
) -> list[PreviewItem]:
    fields = validate_template(template)
    results = []
    for item in items:
        result = PreviewItem(
            book_id=item.book_id,
            library_id=item.library_id,
            current_name="",
            proposed_name="",
            current_path="",
            proposed_path="",
            conflict=False,
            no_change=False,
        )
        book = book_map.get((item.library_id, item.book_id))
        try:
            if not book:
                raise RenameError(
                    failures.get(item.library_id, "Book not found in this library")
                )
            edited = _apply_overrides(book, item.overrides)
            current, root = _resolve_paths(book.abs_path, book.abs_library_root)
            proposed = validate_path(render_path_template(template, edited, root), root)
            result.current_path, result.proposed_path = current, proposed
            result.current_name, result.proposed_name = (
                os.path.relpath(current, root),
                os.path.relpath(proposed, root),
            )
            values = _build_variables(edited)
            result.warnings = [
                f"Missing {field.replace('_', ' ')}"
                for field in sorted(fields)
                if not values[field]
            ]
            result.preview_token = sign_plan(
                fingerprint(template, item, book, current, proposed)
            )
            result.no_change = current == proposed
            if not result.no_change and os.path.lexists(proposed):
                raise RenameError("Destination already exists")
            if not result.no_change and proposed.startswith(current + os.sep):
                raise RenameError("Cannot move a folder inside itself")
        except (RenameError, OSError, ValueError) as e:
            result.conflict = True
            result.error = str(e)
        results.append(result)

    # Check exact and ancestor collisions, conservatively including case and
    # Unicode equivalents for NAS volumes with different filename semantics.
    paths: dict[str, set[int]] = {}
    for i, result in enumerate(results):
        for path in {result.current_path, result.proposed_path} - {""}:
            key = unicodedata.normalize("NFC", path).casefold()
            paths.setdefault(key, set()).add(i)
    for path, owners in paths.items():
        overlapping = set(owners)
        parent = os.path.dirname(path)
        while parent != os.path.dirname(parent):
            overlapping.update(paths.get(parent, set()))
            parent = os.path.dirname(parent)
        if len(overlapping) > 1:
            for i in overlapping:
                results[i].conflict = True
                results[
                    i
                ].error = (
                    "Batch contains duplicate or overlapping source/destination paths"
                )
    return results


async def build_plan(
    client, template: str, items: list[PreviewSelection], fresh: bool = False
) -> list[PreviewItem]:
    validate_template(template)
    book_map, failures = {}, {}
    for library_id in {i.library_id for i in items}:
        try:
            for book in await client.get_library_items(library_id, use_cache=not fresh):
                book_map[(library_id, book.id)] = book
        except ABSClientError as e:
            failures[library_id] = e.detail
    return await asyncio.to_thread(_render, template, items, book_map, failures)
