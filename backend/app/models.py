from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class Author(BaseModel):
    id: str
    name: str


class BookMetadata(BaseModel):
    id: str
    library_id: str
    title: str
    authors: list[Author] = []
    series: Optional[str] = None
    series_id: Optional[str] = None
    series_index: Optional[float] = None
    published_year: Optional[str] = None
    narrator: Optional[str] = None
    abs_path: str
    abs_library_root: str
    is_file: bool = False
    file_extension: str = ""


class Library(BaseModel):
    id: str
    name: str
    folders: list[str] = []


class PreviewRequest(BaseModel):
    template: str
    items: list[dict]


class PreviewItem(BaseModel):
    book_id: str
    library_id: str
    current_name: str
    proposed_name: str
    current_path: str
    proposed_path: str
    conflict: bool
    no_change: bool


class RenameItem(BaseModel):
    book_id: str
    library_id: str
    current_path: str
    overrides: Optional[dict] = None


class RenameRequest(BaseModel):
    template: str
    items: list[RenameItem]
    dry_run: bool = False


class RenameResult(BaseModel):
    book_id: str
    success: bool
    error: Optional[str] = None
    old_path: str
    new_path: str


class RenameResponse(BaseModel):
    results: list[RenameResult]
    scan_triggered: bool


class SeriesUpdateItem(BaseModel):
    book_id: str
    series_id: Optional[str] = None
    series_name: str
    sequence: str


class SeriesUpdateRequest(BaseModel):
    items: list[SeriesUpdateItem]


class SeriesUpdateResult(BaseModel):
    book_id: str
    success: bool


class VerifyItem(BaseModel):
    book_id: str
    library_id: str
    current_path: str


class VerifyRequest(BaseModel):
    items: list[VerifyItem]


class LoginRequest(BaseModel):
    password: str


class CleanupResponse(BaseModel):
    removed: list[str]
