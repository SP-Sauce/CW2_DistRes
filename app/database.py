import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import BACKUP_DIR, DATA_DIR, DB_PATH, DEFAULT_USERS, PRODUCT_FILE_PATH


# Opens a SQLite connection and configures rows so columns can be accessed by name.
@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# Creates required server-side data files before the app accepts client requests.
def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username TEXT PRIMARY KEY, "
            "password TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions ("
            "session_id TEXT PRIMARY KEY, "
            "username TEXT NOT NULL, "
            "connected_at TEXT NOT NULL, "
            "last_seen TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS resource_locks ("
            "resource_name TEXT PRIMARY KEY, "
            "active_writer TEXT, "
            "lock_token TEXT, "
            "owner_server TEXT, "
            "acquired_at TEXT, "
            "expires_at TEXT, "
            "version INTEGER NOT NULL DEFAULT 0"
            ")"
        )
        conn.execute(
            "INSERT OR IGNORE INTO resource_locks("
            "resource_name, active_writer, lock_token, owner_server, acquired_at, expires_at, version"
            ") VALUES (?, NULL, NULL, NULL, NULL, NULL, 0)",
            ("ProductSpecification.txt",),
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS resource_readers ("
            "resource_name TEXT NOT NULL, "
            "username TEXT NOT NULL, "
            "owner_server TEXT, "
            "started_at TEXT NOT NULL, "
            "last_seen TEXT NOT NULL, "
            "expires_at TEXT NOT NULL, "
            "PRIMARY KEY (resource_name, username)"
            ")"
        )
        session_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "last_seen" not in session_columns:
            conn.execute("ALTER TABLE sessions ADD COLUMN last_seen TEXT")
        conn.execute("UPDATE sessions SET last_seen = connected_at WHERE last_seen IS NULL")
        for username, password in DEFAULT_USERS.items():
            conn.execute(
                "INSERT OR IGNORE INTO users(username, password) VALUES (?, ?)",
                (username, password),
            )
        conn.commit()

    if not PRODUCT_FILE_PATH.exists():
        PRODUCT_FILE_PATH.write_text(
            "this our model file to access",
            encoding="utf-8",
        )
