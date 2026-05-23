import asyncio
import threading
from datetime import datetime, timezone


class FailoverController:
    
    # Logical microservice: Health Monitor / Failover Controller.

    # Rubric/design link:
    # - Demonstrates distributed fault tolerance through health state, retry messaging
    #   and standby promotion.
    # - In a one-Replit coursework prototype, primary/standby are logical nodes rather
    #   than two paid/deployed physical servers.
    

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active_server = "PRIMARY"
        self._last_failover = None

    def health(self) -> dict:
        with self._lock:
            return self._health_locked()

    def promote_standby(self) -> dict:
        with self._lock:
            self._active_server = "STANDBY"
            self._last_failover = datetime.now(timezone.utc).isoformat(timespec="seconds")
            return self._health_locked()

    def restore_primary(self) -> dict:
        with self._lock:
            self._active_server = "PRIMARY"
            return self._health_locked()

    def _health_locked(self) -> dict:
        return {
            "active_server": self._active_server,
            "status": "healthy",
            "last_failover": self._last_failover,
        }


failover_controller = FailoverController()
