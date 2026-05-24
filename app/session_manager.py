import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .database import get_connection


# Stores one active browser/client-node session.
@dataclass
class ClientSession:
    session_id: str
    username: str
    connected_at: str


# Tracks connected users in SQLite so standby nodes can continue after failover.
class SessionManager:
    # Serialises local session-table writes inside this server process.
    def __init__(self) -> None:
        self._lock = threading.Lock()

    # Creates a new session for a user unless that username is already connected.
    def create_session(self, username: str) -> Optional[ClientSession]:
        with self._lock:
            with get_connection() as conn:
                existing = conn.execute(
                    "SELECT session_id FROM sessions WHERE username = ?",
                    (username,),
                ).fetchone()
                if existing:
                    return None

                session = ClientSession(
                    session_id=secrets.token_urlsafe(24),
                    username=username,
                    connected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                conn.execute(
                    "INSERT INTO sessions(session_id, username, connected_at) VALUES (?, ?, ?)",
                    (session.session_id, session.username, session.connected_at),
                )
                conn.commit()
                return session

    # Finds a session by token and returns None when the token is missing or invalid.
    def get(self, session_id: str | None) -> Optional[ClientSession]:
        if not session_id:
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT session_id, username, connected_at FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return ClientSession(
            session_id=row["session_id"],
            username=row["username"],
            connected_at=row["connected_at"],
        )

    # Removes a session during logout and returns the username that was disconnected.
    def remove(self, session_id: str | None) -> Optional[str]:
        if not session_id:
            return None
        with self._lock:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT username FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
        return row["username"] if row else None

    # Checks whether a username already owns an active client session.
    def is_user_active(self, username: str) -> bool:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE username = ?",
                (username,),
            ).fetchone()
        return row is not None

    # Returns dashboard-friendly data for every active client node.
    def active_users(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT session_id, username, connected_at FROM sessions ORDER BY connected_at"
            ).fetchall()
        return [
            {
                "username": row["username"],
                "connected_at": row["connected_at"],
                "session_id_tail": row["session_id"][-6:],
            }
            for row in rows
        ]

    # Exports the full session table for primary-to-standby replication.
    def export_sessions(self) -> list[dict]:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT session_id, username, connected_at FROM sessions ORDER BY connected_at"
            ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "username": row["username"],
                "connected_at": row["connected_at"],
            }
            for row in rows
        ]

    # Replaces local sessions with the active server's replicated session table.
    def replace_sessions(self, sessions: list[dict]) -> None:
        with self._lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM sessions")
                conn.executemany(
                    "INSERT INTO sessions(session_id, username, connected_at) VALUES (?, ?, ?)",
                    [
                        (
                            session["session_id"],
                            session["username"],
                            session["connected_at"],
                        )
                        for session in sessions
                    ],
                )
                conn.commit()


session_manager = SessionManager()
