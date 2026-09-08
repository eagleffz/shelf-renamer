from __future__ import annotations

import os
import re
import time

import httpx

from .models import Author, BookMetadata, Library

AUDIO_EXTENSIONS = {
    ".m4b",
    ".mp3",
    ".mp4",
    ".m4a",
    ".flac",
    ".aac",
    ".ogg",
    ".opus",
    ".wma",
}

# How long a fetched library listing stays usable without hitting ABS again.
CACHE_TTL_SECONDS = 60


class ABSClientError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"ABS API error {status_code}: {detail}")


class ABSClient:
    def __init__(self, base_url: str, token: str):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )
        self._items_cache: dict[str, tuple[float, list[BookMetadata]]] = {}
        self._libraries_cache: tuple[float, list[Library]] | None = None

    async def close(self) -> None:
        await self._client.aclose()

    def invalidate(self, library_id: str | None = None) -> None:
        """Drop cached items for one library (or all) plus the library list."""
        if library_id is None:
            self._items_cache.clear()
        else:
            self._items_cache.pop(library_id, None)
        self._libraries_cache = None

    def _check(self, response: httpx.Response) -> httpx.Response:
        if not response.is_success:
            raise ABSClientError(response.status_code, response.text[:500])
        return response

    async def ping(self) -> bool:
        try:
            r = await self._client.get("/ping")
            return r.is_success
        except httpx.HTTPError:
            return False

    async def get_libraries(self, *, use_cache: bool = True) -> list[Library]:
        if use_cache and self._libraries_cache is not None:
            fetched_at, cached = self._libraries_cache
            if time.monotonic() - fetched_at < CACHE_TTL_SECONDS:
                return cached
        try:
            r = self._check(await self._client.get("/api/libraries"))
        except httpx.HTTPError as e:
            raise ABSClientError(503, f"Cannot reach ABS: {e}") from e
        data = r.json()
        libraries = []
        for lib in data.get("libraries", []):
            folders = [f.get("fullPath", "") for f in lib.get("folders", [])]
            libraries.append(Library(id=lib["id"], name=lib["name"], folders=folders))
        self._libraries_cache = (time.monotonic(), libraries)
        return libraries

    async def get_library_items(
        self, library_id: str, lib_root: str = "", *, use_cache: bool = True
    ) -> list[BookMetadata]:
        if use_cache:
            entry = self._items_cache.get(library_id)
            if entry is not None and time.monotonic() - entry[0] < CACHE_TTL_SECONDS:
                return entry[1]

        roots = [lib_root] if lib_root else []
        if not lib_root:
            libs = await self.get_libraries(use_cache=use_cache)
            for lib in libs:
                if lib.id == library_id and lib.folders:
                    roots = lib.folders
                    break

        items: list[dict] = []
        page = 0
        limit = 100
        while True:
            try:
                r = self._check(
                    await self._client.get(
                        f"/api/libraries/{library_id}/items",
                        params={"limit": limit, "page": page},
                    )
                )
            except httpx.HTTPError as e:
                raise ABSClientError(503, f"Cannot reach ABS: {e}") from e
            data = r.json()
            batch = data.get("results", [])
            # An empty page always ends the walk — guards against a missing/wrong
            # "total" spinning this loop forever on identical requests.
            if not batch:
                break
            items.extend(batch)
            total = data.get("total")
            # A missing "total" means "keep going until an empty page", not "zero"
            # — treating it as zero silently truncated libraries to one page.
            if total is not None and len(items) >= total:
                break
            page += 1

        books = []
        for item in items:
            meta = item.get("media", {}).get("metadata", {})

            # ABS returns authors as array of {id,name} objects OR as authorName string.
            # authorName may contain roles like "Übersetzer" (translator) concatenated
            # with real authors — split on ", " and filter single-word non-name tokens.
            raw_authors = meta.get("authors", [])
            if raw_authors:
                authors = [
                    Author(id=a.get("id", ""), name=a.get("name", ""))
                    for a in raw_authors
                ]
            elif meta.get("authorName"):
                parts = [p.strip() for p in meta["authorName"].split(",") if p.strip()]

                # Real names have a space (First Last) or initials with dots (J.R.R.) or hyphens.
                # Single-word role labels like "Übersetzer" (Translator) have none of these.
                def _looks_like_name(s: str) -> bool:
                    return " " in s or "." in s or "-" in s

                names = [p for p in parts if _looks_like_name(p)]
                authors = (
                    [Author(id="", name=n) for n in names]
                    if names
                    else [Author(id="", name=meta["authorName"])]
                )
            else:
                authors = []

            series_name = None
            series_id = None
            series_index = None
            series_list = meta.get("series", [])
            if series_list:
                series_name = series_list[0].get("name")
                series_id = series_list[0].get("id") or None
                seq = series_list[0].get("sequence")
                try:
                    series_index = float(seq) if seq else None
                except (TypeError, ValueError):
                    series_index = None
                # ABS sometimes embeds the index in the name ("Bobiverse #1") with empty sequence
                if series_index is None and series_name:
                    m = re.search(r"#(\d+(?:\.\d+)?)\s*$", series_name)
                    if m:
                        try:
                            series_index = float(m.group(1))
                        except (ValueError, TypeError):
                            pass
            elif meta.get("seriesName"):
                series_name = meta["seriesName"]

            # narrators: array or narratorName string
            narrators = meta.get("narrators", [])
            narrator = narrators[0] if narrators else meta.get("narratorName") or None

            item_path = item.get("path", "")
            matching_roots = [
                root
                for root in roots
                if item_path == root or item_path.startswith(root.rstrip("/") + "/")
            ]
            item_root = max(matching_roots, key=len) if matching_roots else ""
            ext = os.path.splitext(item_path)[1].lower()
            is_file = ext in AUDIO_EXTENSIONS

            books.append(
                BookMetadata(
                    id=item["id"],
                    library_id=library_id,
                    title=meta.get("title") or item.get("id"),
                    authors=authors,
                    series=series_name,
                    series_id=series_id,
                    series_index=series_index,
                    published_year=meta.get("publishedYear"),
                    narrator=narrator,
                    abs_path=item_path,
                    is_file=is_file,
                    file_extension=ext if is_file else "",
                    abs_library_root=item_root,
                )
            )
        self._items_cache[library_id] = (time.monotonic(), books)
        return books

    async def update_series_index(
        self, book_id: str, series_id: str | None, series_name: str, sequence: str
    ) -> bool:
        entry: dict = {"name": series_name, "sequence": sequence}
        if series_id:
            entry["id"] = series_id
        try:
            current = self._check(
                await self._client.get(f"/api/items/{book_id}?expanded=1")
            )
            existing = (
                current.json().get("media", {}).get("metadata", {}).get("series", [])
            )
            matches = [
                s
                for s in existing
                if (series_id and s.get("id") == series_id)
                or s.get("name") == series_name
            ]
            if not matches and len(existing) == 1:
                matches = existing  # normalize an embedded-number series name
            if not matches:
                raise ABSClientError(
                    409, "Series changed in ABS. Refresh before saving."
                )
            updated = [entry if s is matches[0] else s for s in existing]
            r = await self._client.patch(
                f"/api/items/{book_id}/media",
                json={"metadata": {"series": updated}},
            )
            self._check(r)
            return True
        except httpx.HTTPError:
            raise ABSClientError(503, "Cannot reach Audiobookshelf")
        finally:
            # The book's library id is unknown here — dropping everything is cheap.
            self.invalidate()

    async def trigger_scan(self, library_id: str) -> bool:
        try:
            r = await self._client.post(f"/api/libraries/{library_id}/scan")
            return r.is_success
        except httpx.HTTPError:
            return False
        finally:
            self.invalidate(library_id)
