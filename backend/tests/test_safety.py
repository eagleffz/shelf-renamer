import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock, patch

import pytest
from app import auth
from app.config import get_settings
from app.main import app
from app.models import Author, BookMetadata, Library
from app.planner import _resolve_paths, _sorted_volume_map
from app.renamer import RenameError, render_path_template, safe_rename
from fastapi.testclient import TestClient


@pytest.fixture
def library(tmp_path, monkeypatch):
    root = tmp_path / "media"
    root.mkdir()
    settings = get_settings()
    monkeypatch.setattr(settings, "media_root", str(root))
    monkeypatch.setattr(settings, "volume_map", "")
    monkeypatch.setattr(settings, "db_path", str(tmp_path / "history.db"))
    monkeypatch.setattr(settings, "app_password", "")
    _sorted_volume_map.cache_clear()
    books = []
    for i in range(2):
        source = root / f"old{i}"
        source.mkdir()
        (source / "audio.m4b").write_bytes(f"audio-{i}".encode())
        books.append(
            BookMetadata(
                id=f"b{i}",
                library_id="lib",
                title=f"Title {i}",
                authors=[Author(id="a", name="An Author")],
                abs_path=f"/abs/old{i}",
                abs_library_root="/abs",
            )
        )
    with TestClient(app) as client, patch.object(app.state, "abs") as client_abs:
        client_abs.get_library_items = AsyncMock(return_value=books)
        client_abs.get_libraries = AsyncMock(
            return_value=[Library(id="lib", name="Books", folders=["/abs"])]
        )
        client_abs.trigger_scan = AsyncMock(return_value=True)
        yield client, client_abs, books, root
    _sorted_volume_map.cache_clear()


def plan(client, books, template="{title}"):
    result = client.post(
        "/api/preview",
        json={
            "template": template,
            "items": [{"book_id": b.id, "library_id": b.library_id} for b in books],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


def execute(client, preview, template="{title}", **extra):
    return client.post(
        "/api/rename",
        json={
            "template": template,
            "items": [
                {
                    k: p[k]
                    for k in ("book_id", "library_id", "current_path", "preview_token")
                }
                for p in preview
            ],
            **extra,
        },
    )


def test_partial_permission_failure_preserves_results_history_and_scan(library):
    client, abs_client, books, root = library
    preview = plan(client, books)
    actual_move = safe_rename

    def move(old, new, mount):
        if old.endswith("old1"):
            raise PermissionError("Read-only mount")
        actual_move(old, new, mount)

    with patch("app.main.safe_rename", side_effect=move):
        result = execute(client, preview)
    assert result.status_code == 200, result.text
    assert [r["success"] for r in result.json()["results"]] == [True, False]
    assert (root / "Title 0" / "audio.m4b").read_bytes() == b"audio-0"
    assert (root / "old1").exists()
    assert client.get("/api/libraries/lib/history").json() == ["b0"]
    assert [
        r["status"] for r in client.get("/api/libraries/lib/operations").json()
    ] == ["failed", "succeeded"]
    abs_client.trigger_scan.assert_awaited_once_with("lib")


def test_duplicate_destinations_block_entire_batch(library):
    client, _, books, root = library
    books[1].title = books[0].title
    preview = plan(client, books)
    assert all(p["conflict"] for p in preview)
    assert execute(client, preview).status_code == 409
    assert (root / "old0").exists() and (root / "old1").exists()


@pytest.mark.parametrize(
    "change", ["metadata", "template", "source", "token", "override"]
)
def test_stale_or_changed_preview_cannot_move_files(library, change):
    client, _, books, root = library
    preview = plan(client, books)
    template = "{title}"
    if change == "metadata":
        books[0].title = "Changed title"
    if change == "template":
        template = "New/{title}"
    if change == "source":
        preview[0]["current_path"] += "-wrong"
    if change == "token":
        preview[0]["preview_token"] = "invalid"
    if change == "override":
        payload = [
            {
                k: p[k]
                for k in ("book_id", "library_id", "current_path", "preview_token")
            }
            for p in preview
        ]
        payload[0]["overrides"] = {"title": "Different"}
        response = client.post(
            "/api/rename", json={"template": template, "items": payload}
        )
    else:
        response = execute(client, preview, template)
    assert response.status_code == 409
    assert (root / "old0").exists() and (root / "old1").exists()


def test_replaced_source_invalidates_preview(library):
    client, _, books, root = library
    preview = plan(client, books)
    (root / "old0").rename(root / "original")
    (root / "old0").mkdir()
    assert execute(client, preview).status_code == 409


def test_valid_dry_run_does_not_write(library):
    client, abs_client, books, root = library
    assert execute(client, plan(client, books), dry_run=True).status_code == 200
    assert (root / "old0").exists()
    assert client.get("/api/libraries/lib/operations").json() == []
    abs_client.trigger_scan.assert_not_awaited()


def test_missing_books_are_reported_not_silently_dropped(library):
    client, _, books, _ = library
    ghost = books[0].model_copy(update={"id": "missing"})
    preview = plan(client, [ghost])
    assert len(preview) == 1 and preview[0]["conflict"]


@pytest.mark.parametrize(
    "template",
    ["{title", "{unknown}", "{title.__class__}", "{title:>10}", "../{title}"],
)
def test_invalid_templates_return_422(library, template):
    client, _, _, _ = library
    response = client.post("/api/preview", json={"template": template, "items": []})
    assert response.status_code == 422


def test_invalid_item_and_override_return_422(library):
    client, _, _, _ = library
    for item in [
        {"library_id": "lib"},
        {"book_id": "b0", "library_id": "lib", "overrides": {"series_index": "nan"}},
    ]:
        assert (
            client.post(
                "/api/preview", json={"template": "{title}", "items": [item]}
            ).status_code
            == 422
        )


def test_empty_last_segment_keeps_file_extension(library):
    _, _, books, root = library
    book = books[0].model_copy(update={"is_file": True, "file_extension": ".m4b"})
    assert render_path_template("{title}/{series}", book, str(root)).endswith(
        "Title 0/Title 0.m4b"
    )


def test_outside_path_and_unmapped_library_rejected(library, monkeypatch):
    with pytest.raises(RenameError):
        _resolve_paths("/other/book", "/abs")
    monkeypatch.setattr(get_settings(), "volume_map", "/known=/media")
    _sorted_volume_map.cache_clear()
    with pytest.raises(RenameError, match="No volume mapping"):
        _resolve_paths("/abs/book", "/abs")


def test_symlink_source_and_destination_rejected(library, tmp_path):
    _, _, _, root = library
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(RenameError, match="Symlink"):
        safe_rename(str(root / "old0"), str(root / "link" / "book"), str(root))
    with pytest.raises(RenameError, match="Symlink"):
        safe_rename(str(root / "link"), str(root / "new"), str(root))
    (root / "broken").symlink_to(outside / "missing")
    with pytest.raises(RenameError):
        safe_rename(str(root / "old0"), str(root / "broken"), str(root))


def test_concurrent_renames_never_overwrite_destination(tmp_path):
    sources = [tmp_path / "one", tmp_path / "two"]
    for path in sources:
        path.write_text(path.name)
    destination = tmp_path / "target"

    def move(path):
        try:
            safe_rename(str(path), str(destination), str(tmp_path))
            return True
        except RenameError:
            return False

    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(move, sources))
    assert sum(outcomes) == 1
    assert sum(p.exists() for p in sources) == 1
    assert destination.read_text() in {"one", "two"}


def test_kernel_rejects_destination_created_after_preflight(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.write_text("source audio")
    target.write_text("existing audio")
    with (
        patch("app.renamer.os.path.lexists", side_effect=[True, False]),
        pytest.raises(RenameError, match="Target already exists"),
    ):
        safe_rename(str(source), str(target), str(tmp_path))
    assert source.read_text() == "source audio"
    assert target.read_text() == "existing audio"


def test_history_failure_after_move_leaves_pending_record_and_scans(library):
    client, abs_client, books, root = library
    with patch(
        "app.main.finish_operation", side_effect=sqlite3.OperationalError("disk full")
    ):
        response = execute(client, plan(client, books[:1]))
    assert response.status_code == 200
    assert response.json()["results"][0]["success"]
    assert "history" in response.json()["results"][0]["error"]
    assert (root / "Title 0").exists()
    assert client.get("/api/libraries/lib/operations").json()[0]["status"] == "pending"
    abs_client.trigger_scan.assert_awaited_once()


def test_history_failure_before_move_does_not_touch_disk(library):
    client, abs_client, books, root = library
    with patch(
        "app.main.begin_operation", side_effect=sqlite3.OperationalError("disk full")
    ):
        response = execute(client, plan(client, books[:1]))
    assert response.status_code == 200
    assert not response.json()["results"][0]["success"]
    assert (root / "old0").exists()
    abs_client.trigger_scan.assert_not_awaited()


def test_failed_scan_is_explicit(library):
    client, abs_client, books, _ = library
    abs_client.trigger_scan.return_value = False
    response = execute(client, plan(client, books)).json()
    assert response["scan_errors"] == ["lib"]
    assert all(r["success"] for r in response["results"])


def test_cleanup_is_previewed_and_scoped(library):
    client, _, _, root = library
    (root / "empty" / "child").mkdir(parents=True)
    preview = client.post("/api/cleanup", json={"library_id": "lib"}).json()
    assert len(preview["candidates"]) == 2
    assert (root / "empty").exists()
    response = client.post(
        "/api/cleanup",
        json={"library_id": "lib", "dry_run": False, "paths": preview["candidates"]},
    )
    assert len(response.json()["removed"]) == 2
    assert (root / "old0" / "audio.m4b").exists()
    assert (
        client.post(
            "/api/cleanup",
            json={"library_id": "lib", "dry_run": False, "paths": [str(root)]},
        ).status_code
        == 409
    )


def test_repeated_renames_keep_history(library):
    client, _, books, _ = library
    assert execute(client, plan(client, books)).status_code == 200
    for b in books:
        b.abs_path = f"/abs/{b.title}"
    assert (
        execute(client, plan(client, books, "New/{title}"), "New/{title}").status_code
        == 200
    )
    with sqlite3.connect(get_settings().db_path) as db:
        assert db.execute("SELECT COUNT(*) FROM rename_history").fetchone()[0] == 4
    assert len(client.get("/api/libraries/lib/operations").json()) == 4
    client.delete("/api/libraries/lib/history")
    assert len(client.get("/api/libraries/lib/operations").json()) == 4


def test_refresh_bypasses_abs_cache(library):
    client, abs_client, _, _ = library
    client.get("/api/libraries/lib/books?refresh=true")
    abs_client.get_library_items.assert_awaited_with("lib", use_cache=False)


def test_sessions_expire_revoke_and_throttle(library, monkeypatch):
    client, _, _, _ = library
    monkeypatch.setattr(get_settings(), "app_password", "pässword")
    assert client.get("/api/auth/session").status_code == 401
    response = client.post("/api/auth/login", json={"password": "pässword"})
    assert response.status_code == 200
    assert (
        "HttpOnly" in response.headers["set-cookie"]
        and "SameSite=strict" in response.headers["set-cookie"]
    )
    assert "token" not in response.json()
    token = client.cookies.get(auth.COOKIE)
    assert client.get("/api/auth/session").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.set(auth.COOKIE, token)
    assert client.get("/api/auth/session").status_code == 401
    auth.init_auth()
    client.cookies.clear()
    client.post("/api/auth/login", json={"password": "pässword"})
    auth._sessions[client.cookies.get(auth.COOKIE)] = 0
    assert client.get("/api/auth/session").status_code == 401
    auth.init_auth()
    for _ in range(5):
        assert (
            client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
        )
    assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 429


def test_legacy_history_migration_is_idempotent(tmp_path, monkeypatch):
    path = str(tmp_path / "legacy.db")
    monkeypatch.setattr(get_settings(), "db_path", path)
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE rename_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL,
            library_id TEXT NOT NULL, old_path TEXT NOT NULL, new_path TEXT NOT NULL,
            renamed_at TEXT NOT NULL DEFAULT (datetime('now')))""")
        db.execute(
            "CREATE UNIQUE INDEX idx_rename_history_book ON rename_history(book_id,library_id)"
        )
        db.execute(
            "INSERT INTO rename_history (book_id,library_id,old_path,new_path) VALUES ('book','lib','/old','/new')"
        )
    for _ in range(2):
        with TestClient(app) as client:
            assert len(client.get("/api/libraries/lib/operations").json()) == 1
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO rename_history (book_id,library_id,old_path,new_path) VALUES ('book','lib','/new','/newer')"
        )
        assert db.execute("SELECT COUNT(*) FROM rename_history").fetchone()[0] == 2


def test_cross_origin_mutations_rejected(library):
    client, _, _, _ = library
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://other.example"},
            json={"password": ""},
        ).status_code
        == 403
    )
