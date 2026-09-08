from __future__ import annotations

import ctypes
import errno
import os
import re
import stat
import sys
from contextlib import contextmanager
from string import Formatter

from .models import BookMetadata


class RenameError(Exception):
    pass


TEMPLATE_FIELDS = {
    "title",
    "author",
    "author_lf",
    "authors",
    "year",
    "series",
    "series_index",
    "series_index_tag",
    "narrator",
}


def validate_template(template: str) -> set[str]:
    if not template.strip() or len(template) > 1000:
        raise RenameError("Enter a naming template (up to 1000 characters)")
    fields = set()
    try:
        for _literal, field, spec, conversion in Formatter().parse(template):
            if field is None:
                continue
            if field not in TEMPLATE_FIELDS or spec or conversion:
                raise RenameError(f"Unsupported template variable: {{{field}}}")
            fields.add(field)
    except ValueError as e:
        raise RenameError("Unbalanced braces in naming template") from e
    if template.startswith("/") or any(
        p.strip() in {".", ".."} for p in template.split("/")
    ):
        raise RenameError("Use a relative template without '.' or '..' folders")
    return fields


def validate_path(path: str, root: str) -> str:
    root = os.path.realpath(root)
    path = os.path.abspath(path)
    if os.path.commonpath([root, path]) != root or path == root:
        raise RenameError("Path is outside the library root, or is the root itself")
    current = root
    for part in os.path.relpath(path, root).split(os.sep):
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise RenameError(
                "Symlinks inside a library are not supported for renaming"
            )
    return path


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _to_last_first(name: str) -> str:
    parts = name.strip().rsplit(" ", 1)
    if len(parts) == 1:
        return parts[0]
    return f"{parts[1]}, {parts[0]}"


def _format_series_index(idx: float | None) -> str:
    if idx is None:
        return ""
    return str(int(idx)) if idx == int(idx) else str(idx)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[/\\:*?"<>|\x00-\x1f\x7f]', " ", name)
    name = re.sub(r" {2,}", " ", name)
    return name.strip(" .-")


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
    raw_idx = _format_series_index(book.series_index)
    return _SafeDict(
        title=sanitize_filename(book.title),
        author=sanitize_filename(first_author),
        author_lf=sanitize_filename(_to_last_first(first_author)),
        authors=sanitize_filename(all_authors),
        year=sanitize_filename(book.published_year or ""),
        series=sanitize_filename(book.series or ""),
        series_index=raw_idx,
        series_index_tag=f"#{raw_idx}" if raw_idx else "",
        narrator=sanitize_filename(book.narrator or ""),
    )


def render_path_template(template: str, book: BookMetadata, library_root: str) -> str:
    """
    Renders a path-aware template. '/' in the template creates subdirectory levels.
    Empty segments (e.g. {series} when series is None) are dropped automatically.
    Returns the absolute proposed path rooted at library_root.
    For file items, the extension is appended to the last segment.
    """
    validate_template(template)
    variables = _build_variables(book)
    segments = template.split("/")
    rendered: list[str] = []
    for seg in segments:
        part = _cleanup(sanitize_filename(seg.format_map(variables)))
        if not part:
            continue
        rendered.append(part)

    if not rendered:
        fallback = sanitize_filename(book.title or book.id)
        rendered = [fallback or book.id]

    if book.is_file and book.file_extension:
        rendered[-1] += book.file_extension
    if any(len(part.encode("utf-8")) > 255 for part in rendered):
        raise RenameError(
            "A generated filename exceeds 255 bytes; shorten the template or metadata"
        )

    # File items must always reside in a subfolder, never directly in library_root
    if book.is_file and len(rendered) == 1:
        filename = rendered[0]
        ext = book.file_extension
        folder = filename[: -len(ext)] if ext and filename.endswith(ext) else filename
        folder = folder.strip(" .-") or sanitize_filename(book.title or book.id)
        rendered = [folder, filename]

    return os.path.join(library_root, *rendered)


@contextmanager
def _parent_fd(root: str, path: str, create: bool = False):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in os.path.relpath(os.path.dirname(path), root).split(os.sep):
            if part == ".":
                continue
            if create:
                try:
                    os.mkdir(part, dir_fd=fd)
                except FileExistsError:
                    pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)


def safe_rename(old_path: str, new_path: str, root: str | None = None) -> None:
    supplied_root = root or os.path.commonpath(
        [os.path.dirname(old_path), os.path.dirname(new_path)]
    )
    root = os.path.realpath(supplied_root)
    old_path = validate_path(
        os.path.join(root, os.path.relpath(old_path, supplied_root)), root
    )
    new_path = validate_path(
        os.path.join(root, os.path.relpath(new_path, supplied_root)), root
    )
    if not os.path.lexists(old_path):
        raise RenameError(f"Source does not exist: {old_path}")
    if os.path.lexists(new_path):
        raise RenameError(f"Target already exists: {new_path}")
    if os.path.commonpath([old_path, new_path]) == old_path:
        raise RenameError("Cannot move a folder inside itself")
    libc = ctypes.CDLL(None, use_errno=True)
    function = getattr(
        libc, "renameat2" if sys.platform.startswith("linux") else "renameatx_np", None
    )
    if function is None:
        raise RenameError(
            "This filesystem platform does not support safe no-overwrite renames"
        )
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    try:
        with (
            _parent_fd(root, old_path) as src_fd,
            _parent_fd(root, new_path, True) as dst_fd,
        ):
            source = os.stat(
                os.path.basename(old_path), dir_fd=src_fd, follow_symlinks=False
            )
            if stat.S_ISLNK(source.st_mode):
                raise RenameError("Source is a symlink")
            flag = 1 if sys.platform.startswith("linux") else 4
            if function(
                src_fd,
                os.fsencode(os.path.basename(old_path)),
                dst_fd,
                os.fsencode(os.path.basename(new_path)),
                flag,
            ):
                code = ctypes.get_errno()
                if code == errno.EEXIST:
                    raise RenameError(f"Target already exists: {new_path}")
                raise OSError(code, os.strerror(code))
    except OSError as e:
        raise RenameError(f"Cannot rename: {e.strerror or str(e)}") from e
