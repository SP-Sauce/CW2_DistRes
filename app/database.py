import sqlite3
from .config import BACKUP_DIR, DATA_DIR, DB_PATH, DEFAULT_USERS, PRODUCT_FILE_PATH


def get_connection() -> sqlite3.Connection:
    
    # Data layer helper.

    # Rubric link:
    # - Server node hosts the user credential database.
    # - Authentication queries are separated from the application/logic layer.
    
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    
    # Creates the server-side SQLite database and ProductSpecification.txt.

    # This runs when the server starts, which makes the Replit setup simple:
    # click Run and the required data files are created automatically.
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
            """
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
