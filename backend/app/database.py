from __future__ import annotations

import aiosqlite

from .config import get_settings

_CREATE = """
CREATE TABLE IF NOT EXISTS rename_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id TEXT NOT NULL,
    library_id TEXT NOT NULL,
    old_path TEXT NOT NULL,
    new_path TEXT NOT NULL,
    renamed_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

# Existing databases predate the unique index and already hold duplicate
# (book_id, library_id) rows, so they must be collapsed to the newest row per
# pair before the index can be created.
_DEDUPE = """
DELETE FROM rename_history
WHERE id NOT IN (SELECT MAX(id) FROM rename_history GROUP BY book_id, library_id)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rename_history_library ON rename_history(library_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_rename_history_book ON rename_history(book_id, library_id)",
]

_INSERT = (
    "INSERT OR REPLACE INTO rename_history (book_id, library_id, old_path, new_path) "
    "VALUES (?, ?, ?, ?)"
)


async def init_db() -> None:
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.execute(_CREATE)
        await db.execute(_DEDUPE)
        for stmt in _INDEXES:
            await db.execute(stmt)
        await db.commit()


async def record_renames(entries: list[tuple[str, str, str, str]]) -> None:
    """Record a batch of successful renames in one connection."""
    if not entries:
        return
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.executemany(_INSERT, entries)
        await db.commit()


async def get_renamed_book_ids(library_id: str) -> list[str]:
    async with aiosqlite.connect(get_settings().db_path) as db:
        async with db.execute(
            "SELECT DISTINCT book_id FROM rename_history WHERE library_id = ?",
            (library_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def mark_books_verified(entries: list[tuple[str, str, str]]) -> None:
    """Record books already in correct location (old_path == new_path)."""
    if not entries:
        return
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.executemany(_INSERT, [(bid, lid, path, path) for bid, lid, path in entries])
        await db.commit()


async def clear_library_history(library_id: str) -> int:
    async with aiosqlite.connect(get_settings().db_path) as db:
        cursor = await db.execute(
            "DELETE FROM rename_history WHERE library_id = ?",
            (library_id,),
        )
        await db.commit()
        return cursor.rowcount
