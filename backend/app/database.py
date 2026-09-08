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

# Preserve every rename; older versions used a unique per-book index.
_DROP_OLD_UNIQUE_INDEX = "DROP INDEX IF EXISTS idx_rename_history_book"

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rename_history_library ON rename_history(library_id)",
]


async def init_db() -> None:
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.execute(_CREATE)
        await db.execute(_DROP_OLD_UNIQUE_INDEX)
        for stmt in _INDEXES:
            await db.execute(stmt)
        await db.execute("""CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT, book_id TEXT NOT NULL,
            library_id TEXT NOT NULL, old_path TEXT NOT NULL, new_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending', error TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')))
        """)
        await db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version INTEGER PRIMARY KEY)"
        )
        async with db.execute(
            "SELECT 1 FROM schema_migrations WHERE version=1"
        ) as cursor:
            migrated = await cursor.fetchone()
        if not migrated:
            await db.execute("""INSERT INTO operations (book_id,library_id,old_path,new_path,status,created_at)
                SELECT book_id,library_id,old_path,new_path,'succeeded',renamed_at
                FROM rename_history WHERE old_path != new_path""")
            await db.execute("INSERT INTO schema_migrations VALUES (1)")
        await db.commit()


async def get_renamed_book_ids(library_id: str) -> list[str]:
    async with (
        aiosqlite.connect(get_settings().db_path) as db,
        db.execute(
            "SELECT DISTINCT book_id FROM rename_history WHERE library_id = ?",
            (library_id,),
        ) as cursor,
    ):
        rows = await cursor.fetchall()
    return [row[0] for row in rows]


async def clear_library_history(library_id: str) -> int:
    async with aiosqlite.connect(get_settings().db_path) as db:
        cursor = await db.execute(
            "DELETE FROM rename_history WHERE library_id = ?",
            (library_id,),
        )
        await db.commit()
        return cursor.rowcount


async def begin_operation(
    book_id: str, library_id: str, old_path: str, new_path: str
) -> int:
    async with aiosqlite.connect(get_settings().db_path) as db:
        cursor = await db.execute(
            "INSERT INTO operations (book_id,library_id,old_path,new_path) VALUES (?,?,?,?)",
            (book_id, library_id, old_path, new_path),
        )
        await db.commit()
        return cursor.lastrowid


async def finish_operation(
    operation_id: int, success: bool, error: str | None = None
) -> None:
    async with aiosqlite.connect(get_settings().db_path) as db:
        await db.execute(
            "UPDATE operations SET status=?, error=? WHERE id=?",
            ("succeeded" if success else "failed", error, operation_id),
        )
        if success:
            await db.execute(
                "INSERT INTO rename_history (book_id,library_id,old_path,new_path) "
                "SELECT book_id,library_id,old_path,new_path FROM operations WHERE id=?",
                (operation_id,),
            )
        await db.commit()


async def operation_history(library_id: str) -> list[dict]:
    async with aiosqlite.connect(get_settings().db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM operations WHERE library_id=? ORDER BY id DESC LIMIT 500",
            (library_id,),
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]
