import threading
from collections import deque
from typing import Deque, Optional, Set


class ReadWriteCoordinator:
    
    # Logical microservice: ReadWriteCoordinator.

    # Rubric/design link:
    # - Multiple client nodes can read concurrently.
    # - Only one client node can write at a time.
    # - New readers are blocked when a writer is waiting, preventing writer starvation.
    # - All state changes are protected by a mutex to prevent race conditions.

    def __init__(self) -> None:
        self._mutex = threading.Lock()
        self._active_readers: Set[str] = set()
        self._active_writer: Optional[str] = None
        self._waiting_writers: Deque[str] = deque()

    def start_read(self, username: str) -> tuple[bool, str]:
        with self._mutex:
            if self._active_writer:
                return False, f"Blocked: {self._active_writer} is currently writing."
            if self._waiting_writers:
                return False, "Blocked: a writer is waiting, so new reads are paused for fairness."
            self._active_readers.add(username)
            return True, "Read lock granted. Multiple clients may read concurrently."

    def finish_read(self, username: str) -> None:
        with self._mutex:
            self._active_readers.discard(username)
            self._promote_next_writer_if_possible_locked()

    def request_write(self, username: str) -> tuple[str, str]:
        
        # Returns:
        # - GRANTED if the user now owns the write lock.
        # - WAITING if the user has been queued.
        # - ACTIVE if the user already owns the write lock.
        
        with self._mutex:
            if self._active_writer == username:
                return "ACTIVE", "You already own the write lock."

            if username in self._waiting_writers:
                self._promote_next_writer_if_possible_locked()
                if self._active_writer == username:
                    return "GRANTED", "Write lock granted."
                position = list(self._waiting_writers).index(username) + 1
                return "WAITING", f"Waiting for write lock. Queue position: {position}."

            if not self._active_writer and not self._active_readers and not self._waiting_writers:
                self._active_writer = username
                return "GRANTED", "Write lock granted. Only you can write now."

            self._waiting_writers.append(username)
            return "WAITING", f"Write request queued. Queue position: {len(self._waiting_writers)}."

    def finish_write(self, username: str) -> bool:
        with self._mutex:
            if self._active_writer != username:
                return False
            self._active_writer = None
            self._promote_next_writer_if_possible_locked()
            return True

    def cancel_writer(self, username: str) -> None:
        with self._mutex:
            if self._active_writer == username:
                self._active_writer = None
            self._waiting_writers = deque(u for u in self._waiting_writers if u != username)
            self._active_readers.discard(username)
            self._promote_next_writer_if_possible_locked()

    def status(self) -> dict:
        with self._mutex:
            return {
                "active_readers": sorted(self._active_readers),
                "active_writer": self._active_writer,
                "waiting_writers": list(self._waiting_writers),
                "read_count": len(self._active_readers),
            }

    def _promote_next_writer_if_possible_locked(self) -> None:
        if not self._active_writer and not self._active_readers and self._waiting_writers:
            self._active_writer = self._waiting_writers.popleft()


rw_coordinator = ReadWriteCoordinator()
