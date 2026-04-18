"""SQLite database helpers for tokenmap.

Uses Python's built-in sqlite3 module, which is much simpler than
the JS version's sql.js WASM approach. Handles locked databases by
copying to a temp directory.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from typing import Any

from tokenmap.lib.debug import debug


class DbHandle:
    """Wrapper around sqlite3 connection matching the interface adapters expect."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def exec(self, sql: str) -> list[dict[str, Any]]:
        """Execute SQL and return results as list of {columns, values} dicts."""
        try:
            cursor = self._conn.execute(sql)
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            if not columns:
                return []
            values = [list(row) for row in rows]
            return [{"columns": columns, "values": values}]
        except sqlite3.Error:
            return []

    def close(self) -> None:
        """Close the database connection."""
        try:
            self._conn.close()
        except sqlite3.Error:
            pass


def open_db(db_path: str) -> DbHandle:
    """Open a SQLite database, handling locked files by copying to temp dir."""
    try:
        # Try opening read-only first
        uri = f"file:{db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        # Test the connection
        conn.execute("SELECT 1")
        return DbHandle(conn)
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        error_msg = str(e).lower()
        if "locked" in error_msg or "busy" in error_msg or "readonly" in error_msg:
            debug(f"db: file locked/busy, copying to temp dir: {db_path}")
            return _open_copy(db_path)
        # Try regular (non-URI) connection
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            conn.execute("SELECT 1")
            return DbHandle(conn)
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            debug(f"db: regular connection also failed, copying to temp dir: {db_path}")
            return _open_copy(db_path)


def _open_copy(db_path: str) -> DbHandle:
    """Copy the database files to a temp directory and open from there."""
    tmp_dir = tempfile.mkdtemp(prefix="tokenmap-")
    db_name = os.path.basename(db_path)
    tmp_db = os.path.join(tmp_dir, db_name)

    shutil.copy2(db_path, tmp_db)

    # Copy WAL/SHM files if they exist
    for ext in ("-shm", "-wal"):
        src = db_path + ext
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(tmp_dir, db_name + ext))

    conn = sqlite3.connect(tmp_db, timeout=5)

    # Clean up temp files when connection closes
    original_close = conn.close

    def close_and_cleanup() -> None:
        original_close()
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except OSError:
            pass

    conn.close = close_and_cleanup  # type: ignore[assignment]
    return DbHandle(conn)
