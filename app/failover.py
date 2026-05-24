import threading
from datetime import datetime, timezone

from .config import NODE_ID, NODE_ROLE


# Tracks whether this real server process is currently accepting client traffic.
class FailoverController:
    # Primary starts active; standby starts passive until the gateway promotes it.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._node_id = NODE_ID
        self._configured_role = NODE_ROLE
        self._active_role = "primary" if NODE_ROLE == "primary" else "standby"
        self._accepts_client_requests = NODE_ROLE == "primary"
        self._last_failover = None

    # Returns the current node health and active/passive state.
    def health(self) -> dict:
        with self._lock:
            return self._health_locked()

    # Used by the gateway after the primary stops responding.
    def promote_standby(self) -> dict:
        with self._lock:
            self._active_role = "primary"
            self._accepts_client_requests = True
            self._last_failover = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return self._health_locked()

    # Used when manually resetting a standby node back to passive mode.
    def restore_primary(self) -> dict:
        with self._lock:
            self._active_role = self._configured_role
            self._accepts_client_requests = self._configured_role == "primary"
            return self._health_locked()

    # Prevents direct client writes to a passive standby.
    def accepts_client_requests(self) -> bool:
        with self._lock:
            return self._accepts_client_requests

    # Builds the health payload while the caller already holds the lock.
    def _health_locked(self) -> dict:
        return {
            "node_id": self._node_id,
            "configured_role": self._configured_role,
            "active_role": self._active_role,
            "active_server": self._node_id,
            "accepts_client_requests": self._accepts_client_requests,
            "status": "healthy",
            "last_failover": self._last_failover,
        }


failover_controller = FailoverController()
