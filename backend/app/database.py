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


async def init_db() -> None:
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.execute(_CREATE)
        await db.commit()


async def record_rename(book_id: str, library_id: str, old_path: str, new_path: str) -> None:
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.execute(
            "INSERT INTO rename_history (book_id, library_id, old_path, new_path) VALUES (?, ?, ?, ?)",
            (book_id, library_id, old_path, new_path),
        )
        await db.commit()


async def get_renamed_book_ids(library_id: str) -> list[str]:
    async with aiosqlite.connect(get_settings().db_path) as db:
        async with db.execute(
            "SELECT DISTINCT book_id FROM rename_history WHERE library_id = ?",
            (library_id,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [row[0] for row in rows]
