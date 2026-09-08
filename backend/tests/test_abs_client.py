import json

import httpx
import pytest
from app.abs_client import ABSClient, ABSClientError


def _make_client(transport: httpx.MockTransport) -> ABSClient:
    client = ABSClient("http://abs.local", "test-token")
    client._client = httpx.AsyncClient(
        base_url="http://abs.local",
        headers={"Authorization": "Bearer test-token"},
        transport=transport,
    )
    return client


def _lib_response():
    return httpx.Response(
        200,
        json={
            "libraries": [
                {
                    "id": "lib1",
                    "name": "Audiobooks",
                    "folders": [{"fullPath": "/abs/books"}],
                }
            ]
        },
    )


def _items_response():
    return httpx.Response(
        200,
        json={
            "total": 1,
            "results": [
                {
                    "id": "book1",
                    "path": "/abs/books/Terry Pratchett/Guards Guards",
                    "media": {
                        "metadata": {
                            "title": "Guards! Guards!",
                            "authors": [{"id": "a1", "name": "Terry Pratchett"}],
                            "series": [{"name": "Discworld", "sequence": "8"}],
                            "publishedYear": "1989",
                            "narrators": ["Nigel Planer"],
                        }
                    },
                }
            ],
        },
    )


@pytest.mark.anyio
async def test_get_libraries():
    def handler(req):
        if req.url.path == "/api/libraries":
            return _lib_response()
        return httpx.Response(404)

    client = _make_client(httpx.MockTransport(handler))
    libs = await client.get_libraries()
    assert len(libs) == 1
    assert libs[0].id == "lib1"
    assert libs[0].folders == ["/abs/books"]
    await client.close()


@pytest.mark.anyio
async def test_get_library_items():
    def handler(req):
        if req.url.path == "/api/libraries":
            return _lib_response()
        if "/items" in req.url.path:
            return _items_response()
        return httpx.Response(404)

    client = _make_client(httpx.MockTransport(handler))
    books = await client.get_library_items("lib1")
    assert len(books) == 1
    assert books[0].title == "Guards! Guards!"
    assert books[0].series == "Discworld"
    assert books[0].series_index == 8.0
    assert books[0].published_year == "1989"
    await client.close()


@pytest.mark.anyio
async def test_library_items_cached_until_invalidated():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if req.url.path == "/api/libraries":
            return _lib_response()
        if "/items" in req.url.path:
            return _items_response()
        return httpx.Response(404)

    client = _make_client(httpx.MockTransport(handler))
    await client.get_library_items("lib1")
    after_first = calls["n"]
    assert after_first > 0

    await client.get_library_items("lib1")
    assert calls["n"] == after_first  # served from cache, no HTTP

    client.invalidate()
    await client.get_library_items("lib1")
    assert calls["n"] == after_first * 2
    await client.close()


@pytest.mark.anyio
async def test_library_items_not_cached_on_error():
    def handler(req):
        if req.url.path == "/api/libraries":
            return _lib_response()
        return httpx.Response(500, text="boom")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(ABSClientError):
        await client.get_library_items("lib1")
    assert "lib1" not in client._items_cache
    await client.close()


@pytest.mark.anyio
async def test_pagination_stops_on_empty_page_without_total():
    pages: list[int] = []

    def handler(req):
        if req.url.path == "/api/libraries":
            return _lib_response()
        page = int(req.url.params.get("page", 0))
        pages.append(page)
        if page == 0:
            # No "total" key at all — must not be read as zero.
            body = _items_response().json()
            body.pop("total")
            return httpx.Response(200, json=body)
        return httpx.Response(200, json={"results": []})

    client = _make_client(httpx.MockTransport(handler))
    books = await client.get_library_items("lib1")
    assert pages == [0, 1]  # second page was fetched, empty page ended the walk
    assert len(books) == 1
    await client.close()


@pytest.mark.anyio
async def test_unauthorized_raises():
    def handler(req):
        return httpx.Response(401, text="Unauthorized")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(ABSClientError) as exc_info:
        await client.get_libraries()
    assert exc_info.value.status_code == 401
    await client.close()


async def test_multiple_library_folders_use_each_items_root():
    def handler(req):
        if req.url.path == "/api/libraries":
            data = _lib_response().json()
            data["libraries"][0]["folders"].append({"fullPath": "/abs/second"})
            return httpx.Response(200, json=data)
        data = _items_response().json()
        data["results"][0]["path"] = "/abs/second/A Book"
        return httpx.Response(200, json=data)

    client = _make_client(httpx.MockTransport(handler))
    assert (await client.get_library_items("lib1"))[0].abs_library_root == "/abs/second"
    await client.close()


async def test_series_update_preserves_other_memberships():
    patched = []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "media": {
                        "metadata": {
                            "series": [
                                {"id": "first", "name": "Series", "sequence": "1"},
                                {"id": "other", "name": "Collection", "sequence": "9"},
                            ]
                        }
                    }
                },
            )
        patched.append(json.loads(req.content))
        return httpx.Response(200, json={})

    client = _make_client(httpx.MockTransport(handler))
    assert await client.update_series_index("book", "first", "Series", "2")
    assert patched[0]["metadata"]["series"] == [
        {"id": "first", "name": "Series", "sequence": "2"},
        {"id": "other", "name": "Collection", "sequence": "9"},
    ]
    await client.close()
