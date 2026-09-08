from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Author(BaseModel):
    id: str
    name: str


class BookMetadata(BaseModel):
    id: str
    library_id: str
    title: str
    authors: list[Author] = []
    series: str | None = None
    series_id: str | None = None
    series_index: float | None = None
    published_year: str | None = None
    narrator: str | None = None
    abs_path: str
    abs_library_root: str
    is_file: bool = False
    file_extension: str = ""


class Library(BaseModel):
    id: str
    name: str
    folders: list[str] = []


class PreviewSelection(BaseModel):
    book_id: str = Field(min_length=1)
    library_id: str = Field(min_length=1)
    overrides: dict[str, str] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def valid_overrides(cls, value):
        if set(value) - {
            "author",
            "title",
            "series",
            "series_index",
            "narrator",
            "year",
        }:
            raise ValueError("Unknown metadata override")
        if any(len(v) > 1000 for v in value.values()):
            raise ValueError("Metadata override is too long")
        if "title" in value and not value["title"].strip():
            raise ValueError("Title must not be empty")
        if value.get("series_index"):
            import math

            if not math.isfinite(float(value["series_index"])):
                raise ValueError("Series index must be a finite number")
        return value


class PreviewRequest(BaseModel):
    template: str = Field(min_length=1, max_length=1000)
    items: list[PreviewSelection] = Field(max_length=10000)


class PreviewItem(BaseModel):
    book_id: str
    library_id: str
    current_name: str
    proposed_name: str
    current_path: str
    proposed_path: str
    conflict: bool
    no_change: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    preview_token: str = ""


class RenameItem(PreviewSelection):
    current_path: str
    preview_token: str = ""


class RenameRequest(BaseModel):
    template: str = Field(min_length=1, max_length=1000)
    items: list[RenameItem] = Field(max_length=10000)
    dry_run: bool = False


class RenameResult(BaseModel):
    book_id: str
    success: bool
    error: str | None = None
    old_path: str
    new_path: str


class RenameResponse(BaseModel):
    results: list[RenameResult]
    scan_triggered: bool
    scan_errors: list[str] = Field(default_factory=list)


class SeriesUpdateItem(BaseModel):
    book_id: str
    series_id: str | None = None
    series_name: str
    sequence: str

    @field_validator("sequence")
    @classmethod
    def valid_sequence(cls, value):
        import math

        if value.strip() and not math.isfinite(float(value)):
            raise ValueError("Sequence must be a finite number or empty")
        return value.strip()


class SeriesUpdateRequest(BaseModel):
    items: list[SeriesUpdateItem] = Field(max_length=10000)


class SeriesUpdateResult(BaseModel):
    book_id: str
    success: bool
    error: str | None = None


class LoginRequest(BaseModel):
    password: str = Field(max_length=1000)
