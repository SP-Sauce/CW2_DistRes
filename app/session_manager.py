import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional


# Stores one active browser/client-node session.
@dataclass
class ClientSession:
    session_id: str
    username: str
    connected_at: str


# Logical service that tracks connected users and prevents duplicate logins.
class SessionManager:
    # Creates the lock and in-memory session table used by all client nodes.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, ClientSession] = {}

    # Creates a new session for a user unless that username is already connected.
    def create_session(self, username: str) -> Optional[ClientSession]:
        with self._lock:
            if self.is_user_active(username):
                return None
            session = ClientSession(
                session_id=secrets.token_urlsafe(24),
                username=username,
                connected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            self._sessions[session.session_id] = session
            return session

    # Finds a session by token and returns None when the token is missing or invalid.
    def get(self, session_id: str | None) -> Optional[ClientSession]:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.get(session_id)

    # Removes a session during logout and returns the username that was disconnected.
    def remove(self, session_id: str | None) -> Optional[str]:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.pop(session_id, None)
            return session.username if session else None

    # Checks whether a username already owns an active client session.
    def is_user_active(self, username: str) -> bool:
        return any(s.username == username for s in self._sessions.values())

    # Returns dashboard-friendly data for every active client node.
    def active_users(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "username": s.username,
                    "connected_at": s.connected_at,
                    "session_id_tail": s.session_id[-6:],
                }
                for s in self._sessions.values()
            ]


session_manager = SessionManager()
