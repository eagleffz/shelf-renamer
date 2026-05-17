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
    # strip empty parens/brackets left by missing variables
    name = re.sub(r"\(\s*\)", "", name)
    name = re.sub(r"\[\s*\]", "", name)
    # collapse multiple spaces
    name = re.sub(r" {2,}", " ", name)
    # collapse multiple dashes (but preserve intentional " - " separators)
    name = re.sub(r"-{2,}", "-", name)
    # strip trailing/leading separator artifacts
    name = re.sub(r"\s+-\s*$", "", name)
    name = re.sub(r"^\s*-\s+", "", name)
    return name.strip(" .-")


def render_template(template: str, book: BookMetadata) -> str:
    first_author = book.authors[0].name if book.authors else ""
    all_authors = " & ".join(a.name for a in book.authors) if book.authors else ""

    variables = _SafeDict(
        title=sanitize_filename(book.title),
        author=sanitize_filename(first_author),
        author_lf=sanitize_filename(_to_last_first(first_author)),
        authors=sanitize_filename(all_authors),
        year=sanitize_filename(book.published_year or ""),
        series=sanitize_filename(book.series or ""),
        series_index=_format_series_index(book.series_index),
        narrator=sanitize_filename(book.narrator or ""),
    )
    result = template.format_map(variables)
    base = _cleanup(result)
    # append original extension for single-file items
    if book.is_file and book.file_extension:
        return base + book.file_extension
    return base


def build_proposed_path(current_path: str, new_folder_name: str) -> str:
    return os.path.join(os.path.dirname(current_path), new_folder_name)


def safe_rename(old_path: str, new_path: str) -> None:
    if not os.path.exists(old_path):
        raise RenameError(f"Source does not exist: {old_path}")
    if os.path.exists(new_path):
        raise RenameError(f"Target already exists: {new_path}")
    os.rename(old_path, new_path)
