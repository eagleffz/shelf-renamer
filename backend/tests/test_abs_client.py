import pytest
import httpx
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
async def test_unauthorized_raises():
    def handler(req):
        return httpx.Response(401, text="Unauthorized")

    client = _make_client(httpx.MockTransport(handler))
    with pytest.raises(ABSClientError) as exc_info:
        await client.get_libraries()
    assert exc_info.value.status_code == 401
    await client.close()
