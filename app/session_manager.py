import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import SESSION_STALE_AFTER_SECONDS
from .database import get_connection


# Stores one active browser/client-node session.
@dataclass
class ClientSession:
    session_id: str
    username: str
    connected_at: str
    last_seen: str


# Tracks connected users in SQLite so every active node sees the same sessions.
class SessionManager:
    # Serialises local session-table writes inside this server process.
    def __init__(self) -> None:
        self._lock = threading.Lock()

    # Creates a new session for a user unless that username is already connected.
    def create_session(self, username: str) -> Optional[ClientSession]:
        with self._lock:
            with get_connection() as conn:
                self._remove_stale_sessions_locked(conn)
                existing = conn.execute(
                    "SELECT session_id FROM sessions WHERE username = ?",
                    (username,),
                ).fetchone()
                if existing:
                    return None

                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                session = ClientSession(
                    session_id=secrets.token_urlsafe(24),
                    username=username,
                    connected_at=now,
                    last_seen=now,
                )
                conn.execute(
                    "INSERT INTO sessions(session_id, username, connected_at, last_seen) VALUES (?, ?, ?, ?)",
                    (session.session_id, session.username, session.connected_at, session.last_seen),
                )
                conn.commit()
                return session

    # Finds a session by token and returns None when the token is missing or invalid.
    def get(self, session_id: str | None) -> Optional[ClientSession]:
        if not session_id:
            return None
        with get_connection() as conn:
            row = conn.execute(
                "SELECT session_id, username, connected_at, last_seen FROM sessions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        if not row:
            return None
        return ClientSession(
            session_id=row["session_id"],
            username=row["username"],
            connected_at=row["connected_at"],
            last_seen=row["last_seen"],
        )

    # Refreshes the activity timestamp for a client that is still polling or acting.
    def touch(self, session_id: str | None) -> None:
        if not session_id:
            return
        with get_connection() as conn:
            conn.execute(
                "UPDATE sessions SET last_seen = ? WHERE session_id = ?",
                (datetime.now(timezone.utc).isoformat(timespec="seconds"), session_id),
            )
            conn.commit()

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

    # Removes all sessions for one username, used when a browser restart loses its token.
    def remove_user(self, username: str) -> int:
        with self._lock:
            with get_connection() as conn:
                cursor = conn.execute("DELETE FROM sessions WHERE username = ?", (username,))
                conn.commit()
                return cursor.rowcount

    # Checks whether a username already owns an active client session.
    def is_user_active(self, username: str) -> bool:
        with self._lock:
            with get_connection() as conn:
                self._remove_stale_sessions_locked(conn)
                row = conn.execute(
                    "SELECT 1 FROM sessions WHERE username = ?",
                    (username,),
                ).fetchone()
                conn.commit()
        return row is not None

    # Returns dashboard-friendly data for every active client node.
    def active_users(self) -> list[dict]:
        with self._lock:
            with get_connection() as conn:
                self._remove_stale_sessions_locked(conn)
                rows = conn.execute(
                    "SELECT session_id, username, connected_at, last_seen FROM sessions ORDER BY connected_at"
                ).fetchall()
                conn.commit()
        return [
            {
                "username": row["username"],
                "connected_at": row["connected_at"],
                "last_seen": row["last_seen"],
                "session_id_tail": row["session_id"][-6:],
            }
            for row in rows
        ]

    # Exports the full session table for optional snapshot/replication support.
    def export_sessions(self) -> list[dict]:
        with self._lock:
            with get_connection() as conn:
                self._remove_stale_sessions_locked(conn)
                rows = conn.execute(
                    "SELECT session_id, username, connected_at, last_seen FROM sessions ORDER BY connected_at"
                ).fetchall()
                conn.commit()
        return [
            {
                "session_id": row["session_id"],
                "username": row["username"],
                "connected_at": row["connected_at"],
                "last_seen": row["last_seen"],
            }
            for row in rows
        ]

    # Replaces local sessions with the active server's replicated session table.
    def replace_sessions(self, sessions: list[dict]) -> None:
        with self._lock:
            with get_connection() as conn:
                conn.execute("DELETE FROM sessions")
                conn.executemany(
                    "INSERT INTO sessions(session_id, username, connected_at, last_seen) VALUES (?, ?, ?, ?)",
                    [
                        (
                            session["session_id"],
                            session["username"],
                            session["connected_at"],
                            session.get("last_seen", session["connected_at"]),
                        )
                        for session in sessions
                    ],
                )
                conn.commit()

    # Drops sessions whose browser heartbeat has stopped, usually after Ctrl+C/close.
    def _remove_stale_sessions_locked(self, conn) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=SESSION_STALE_AFTER_SECONDS)
        cursor = conn.execute(
            "DELETE FROM sessions WHERE last_seen IS NULL OR last_seen < ?",
            (cutoff.isoformat(timespec="seconds"),),
        )
        return cursor.rowcount


session_manager = SessionManager()
