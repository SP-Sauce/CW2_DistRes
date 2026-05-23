import sqlite3
from .config import BACKUP_DIR, DATA_DIR, DB_PATH, DEFAULT_USERS, PRODUCT_FILE_PATH


# Opens a SQLite connection and configures rows so columns can be accessed by name.
def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


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
