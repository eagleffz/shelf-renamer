import sqlite3
from unittest.mock import AsyncMock, patch

import pytest
from app.config import get_settings
from app.main import app
from app.models import Author, BookMetadata, Library
from fastapi.testclient import TestClient


def _make_book() -> BookMetadata:
    return BookMetadata(
        id="book1",
        library_id="lib1",
        title="Guards! Guards!",
        authors=[Author(id="a1", name="Terry Pratchett")],
        series="Discworld",
        series_index=8.0,
        published_year="1989",
        narrator="Nigel Planer",
        abs_path="/abs/books/Terry Pratchett/Guards Guards",
        abs_library_root="/abs/books",
        is_file=False,
        file_extension="",
    )


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    with patch.object(app.state, "abs") as mock_abs:
        mock_abs.ping = AsyncMock(return_value=True)
        r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_config(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert "default_template" in r.json()


def test_libraries(client):
    with patch.object(app.state, "abs") as mock_abs:
        mock_abs.get_libraries = AsyncMock(
            return_value=[Library(id="lib1", name="Audiobooks", folders=["/abs/books"])]
        )
        r = client.get("/api/libraries")
    assert r.status_code == 200
    data = r.json()
    assert data[0]["id"] == "lib1"


def test_preview(client):
    book = _make_book()
    with patch.object(app.state, "abs") as mock_abs:
        mock_abs.get_library_items = AsyncMock(return_value=[book])
        r = client.post(
            "/api/preview",
            json={
                "template": "{author} - {title} ({year})",
                "items": [{"book_id": "book1", "library_id": "lib1"}],
            },
        )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert "Terry Pratchett" in items[0]["proposed_name"]
    assert "1989" in items[0]["proposed_name"]


def test_preview_spans_multiple_libraries(client):
    book1 = _make_book()
    book2 = _make_book().model_copy(
        update={
            "id": "book2",
            "library_id": "lib2",
            "title": "Mort",
            "abs_path": "/abs/other/Terry Pratchett/Mort",
            "abs_library_root": "/abs/other",
        }
    )
    by_library = {"lib1": [book1], "lib2": [book2]}

    with patch.object(app.state, "abs") as mock_abs:
        mock_abs.get_library_items = AsyncMock(
            side_effect=lambda lib_id, *a, **kw: by_library[lib_id]
        )
        r = client.post(
            "/api/preview",
            json={
                "template": "{author} - {title}",
                "items": [
                    {"book_id": "book1", "library_id": "lib1"},
                    {"book_id": "book2", "library_id": "lib2"},
                ],
            },
        )
    assert r.status_code == 200
    items = r.json()
    assert [i["book_id"] for i in items] == ["book1", "book2"]
    assert [i["library_id"] for i in items] == ["lib1", "lib2"]


def test_client_cannot_mark_arbitrary_paths_verified(client):
    payload = {
        "items": [
            {
                "book_id": "verify1",
                "library_id": "libverify",
                "current_path": "/media/Terry Pratchett/Mort",
            }
        ]
    }
    assert (
        client.post("/api/libraries/libverify/verify", json=payload).status_code == 404
    )

    r = client.get("/api/libraries/libverify/history")
    assert r.status_code == 200
    assert r.json() == []

    # DISTINCT would hide a duplicate — check the table itself.
    with sqlite3.connect(get_settings().db_path) as db:
        rows = db.execute(
            "SELECT COUNT(*) FROM rename_history WHERE library_id = ?", ("libverify",)
        ).fetchone()[0]
    assert rows == 0


def test_preview_empty_template(client):
    r = client.post(
        "/api/preview",
        json={"template": "  ", "items": []},
    )
    assert r.status_code == 422


def test_rename_dry_run_rejects_missing_source(client):
    book = _make_book()
    with patch.object(app.state, "abs") as mock_abs:
        mock_abs.get_library_items = AsyncMock(return_value=[book])
        mock_abs.trigger_scan = AsyncMock(return_value=True)
        r = client.post(
            "/api/rename",
            json={
                "template": "{author} - {title}",
                "dry_run": True,
                "items": [
                    {
                        "book_id": "book1",
                        "library_id": "lib1",
                        "current_path": "/media/Terry Pratchett/Guards Guards",
                    }
                ],
            },
        )
    assert r.status_code == 409
    mock_abs.trigger_scan.assert_not_awaited()
