from __future__ import annotations

import os
import re
from typing import Optional
from .models import BookMetadata


class RenameError(Exception):
    pass


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _to_last_first(name: str) -> str:
    parts = name.strip().rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0]
    return f"{parts[1]}, {parts[0]}"


def _format_series_index(idx: Optional[float]) -> str:
    if idx is None:
        return ""
    return str(int(idx)) if idx == int(idx) else str(idx)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|]', "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = re.sub(r" {2,}", " ", name)
    return name.strip(" .")


def _cleanup(name: str) -> str:
    name = re.sub(r"\(\s*\)", "", name)
    name = re.sub(r"\[\s*\]", "", name)
    name = re.sub(r" {2,}", " ", name)
    # collapse repeated separators: " - - " or "– –" → " - "
    name = re.sub(r"(\s*[-–]\s*){2,}", " - ", name)
    name = re.sub(r"\s+-\s*$", "", name)
    name = re.sub(r"^\s*-\s+", "", name)
    return name.strip(" .-")


def _build_variables(book: BookMetadata) -> _SafeDict:
    first_author = book.authors[0].name if book.authors else ""
    all_authors = " & ".join(a.name for a in book.authors) if book.authors else ""
    return _SafeDict(
        title=sanitize_filename(book.title),
        author=sanitize_filename(first_author),
        author_lf=sanitize_filename(_to_last_first(first_author)),
        authors=sanitize_filename(all_authors),
        year=sanitize_filename(book.published_year or ""),
        series=sanitize_filename(book.series or ""),
        series_index=_format_series_index(book.series_index),
        narrator=sanitize_filename(book.narrator or ""),
    )


def render_path_template(template: str, book: BookMetadata, library_root: str) -> str:
    """
    Renders a path-aware template. '/' in the template creates subdirectory levels.
    Empty segments (e.g. {series} when series is None) are dropped automatically.
    Returns the absolute proposed path rooted at library_root.
    For file items, the extension is appended to the last segment.
    """
    variables = _build_variables(book)
    segments = template.split("/")
    rendered: list[str] = []
    for i, seg in enumerate(segments):
        part = _cleanup(seg.format_map(variables))
        if not part:
            continue
        # append extension only to the final segment of a file item
        if book.is_file and book.file_extension and i == len(segments) - 1:
            part = part + book.file_extension
        rendered.append(part)

    if not rendered:
        rendered = [book.title or book.id]

    return os.path.join(library_root, *rendered)


def safe_rename(old_path: str, new_path: str) -> None:
    if not os.path.exists(old_path):
        raise RenameError(f"Source does not exist: {old_path}")
    if os.path.exists(new_path):
        raise RenameError(f"Target already exists: {new_path}")
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    os.rename(old_path, new_path)
