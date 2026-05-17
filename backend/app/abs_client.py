from __future__ import annotations

import os
import httpx
from .models import Author, BookMetadata, Library

AUDIO_EXTENSIONS = {'.m4b', '.mp3', '.mp4', '.m4a', '.flac', '.aac', '.ogg', '.opus', '.wma'}


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

    async def close(self) -> None:
        await self._client.aclose()

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

    async def get_libraries(self) -> list[Library]:
        try:
            r = self._check(await self._client.get("/api/libraries"))
        except httpx.HTTPError as e:
            raise ABSClientError(503, f"Cannot reach ABS: {e}") from e
        data = r.json()
        libraries = []
        for lib in data.get("libraries", []):
            folders = [f.get("fullPath", "") for f in lib.get("folders", [])]
            libraries.append(Library(id=lib["id"], name=lib["name"], folders=folders))
        return libraries

    async def get_library_items(self, library_id: str) -> list[BookMetadata]:
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
            items.extend(batch)
            if len(items) >= data.get("total", 0):
                break
            page += 1

        # determine library root (first folder)
        libs = await self.get_libraries()
        lib_root = ""
        for lib in libs:
            if lib.id == library_id and lib.folders:
                lib_root = lib.folders[0]
                break

        books = []
        for item in items:
            meta = item.get("media", {}).get("metadata", {})

            # ABS returns authors as array of {id,name} objects OR as authorName string.
            # authorName may contain roles like "Übersetzer" (translator) concatenated
            # with real authors — split on ", " and filter single-word non-name tokens.
            raw_authors = meta.get("authors", [])
            if raw_authors:
                authors = [Author(id=a.get("id", ""), name=a.get("name", "")) for a in raw_authors]
            elif meta.get("authorName"):
                parts = [p.strip() for p in meta["authorName"].split(",") if p.strip()]
                # Real names have a space (First Last) or initials with dots (J.R.R.) or hyphens.
                # Single-word role labels like "Übersetzer" (Translator) have none of these.
                def _looks_like_name(s: str) -> bool:
                    return " " in s or "." in s or "-" in s
                names = [p for p in parts if _looks_like_name(p)]
                authors = [Author(id="", name=n) for n in names] if names else [Author(id="", name=meta["authorName"])]
            else:
                authors = []

            series_name = None
            series_index = None
            series_list = meta.get("series", [])
            if series_list:
                series_name = series_list[0].get("name")
                seq = series_list[0].get("sequence")
                try:
                    series_index = float(seq) if seq else None
                except (TypeError, ValueError):
                    series_index = None
            elif meta.get("seriesName"):
                series_name = meta["seriesName"]

            # narrators: array or narratorName string
            narrators = meta.get("narrators", [])
            narrator = narrators[0] if narrators else meta.get("narratorName") or None

            item_path = item.get("path", "")
            ext = os.path.splitext(item_path)[1].lower()
            is_file = ext in AUDIO_EXTENSIONS

            books.append(
                BookMetadata(
                    id=item["id"],
                    library_id=library_id,
                    title=meta.get("title") or item.get("id"),
                    authors=authors,
                    series=series_name,
                    series_index=series_index,
                    published_year=meta.get("publishedYear"),
                    narrator=narrator,
                    abs_path=item_path,
                    is_file=is_file,
                    file_extension=ext if is_file else "",
                    abs_library_root=lib_root,
                )
            )
        return books

    async def trigger_scan(self, library_id: str) -> bool:
        try:
            r = await self._client.post(f"/api/libraries/{library_id}/scan")
            return r.is_success
        except httpx.HTTPError:
            return False
