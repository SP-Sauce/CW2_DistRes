import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional


@dataclass
class ClientSession:
    session_id: str
    username: str
    connected_at: str


class SessionManager:
    
    # Logical microservice: SessionManager.

    # Rubric/design link:
    # - Manages active client nodes on the server.
    # - Prevents the same username opening multiple active sessions.
    # - Provides state for UI demonstration of connected clients.
    

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: Dict[str, ClientSession] = {}

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

    def get(self, session_id: str | None) -> Optional[ClientSession]:
        if not session_id:
            return None
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str | None) -> Optional[str]:
        if not session_id:
            return None
        with self._lock:
            session = self._sessions.pop(session_id, None)
            return session.username if session else None

    def is_user_active(self, username: str) -> bool:
        return any(s.username == username for s in self._sessions.values())

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
