import threading
from datetime import datetime, timezone


# Logical health monitor that tracks primary/standby server state for the demo.
class FailoverController:
    # Starts the simulated distributed system with the primary server active.
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_server = "PRIMARY"
        self._last_failover = None

    # Returns the current active server and failover status.
    def health(self) -> dict:
        with self._lock:
            return self._health_locked()

    # Marks the standby server as active and records when failover occurred.
    def promote_standby(self) -> dict:
        with self._lock:
            self._active_server = "STANDBY"
            self._last_failover = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return self._health_locked()

    # Restores the primary server as the active logical server.
    def restore_primary(self) -> dict:
        with self._lock:
            self._active_server = "PRIMARY"
            return self._health_locked()

    # Builds the health payload while the caller already holds the lock.
    def _health_locked(self) -> dict:
        return {
            "active_server": self._active_server,
            "status": "healthy",
            "last_failover": self._last_failover,
        }


failover_controller = FailoverController()
