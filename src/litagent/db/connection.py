"""SQLite connection helper.

Raw `sqlite3`, not an ORM (see CLAUDE.md's redesign log): the whole database
is a single file committed to the `state` branch by the GitHub Actions
workflow, so there's no separate server/migration story to manage -- just a
file and the schema that describes it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Columns added to an existing table after it first shipped. `CREATE TABLE
# IF NOT EXISTS` (schema.sql) only creates a table that doesn't exist yet --
# it never alters one that already does, and the whole point of this file
# being a single committed database is that real, already-populated copies
# of it exist. Each entry here is applied via `ALTER TABLE ... ADD COLUMN`
# if missing, forever (append, never remove) -- the lightweight equivalent
# of a migration for a file-based DB with no migration framework.
_ADDED_COLUMNS: list[tuple[str, str, str]] = [
    # (table, column, column definition)
    ("landscape_entries", "delivered_at", "TEXT"),
]


def get_connection(db_path: str | Path) -> sqlite3.Connection:
    """Open (creating if necessary) the litagent SQLite database at `db_path`.

    Applies `schema.sql` every time via `CREATE TABLE IF NOT EXISTS` -- cheap,
    and means a fresh checkout of the `state` branch with an empty/missing
    file still works without a separate init step. Then applies any pending
    `_ADDED_COLUMNS` migrations, so an older database file catches up too.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_PATH.read_text())
    for table, column, definition in _ADDED_COLUMNS:
        _ensure_column(conn, table, column, definition)
    conn.commit()
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
