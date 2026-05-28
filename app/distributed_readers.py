import sqlite3
from datetime import datetime, timedelta, timezone

from .config import DISTRIBUTED_READ_LEASE_SECONDS
from .database import get_connection
from .distributed_lock import RESOURCE_NAME, _parse_dt


class DistributedReadTracker:
    # Shared reader table so active-active nodes report the same active readers.
    def __init__(self, resource_name: str = RESOURCE_NAME) -> None:
        self.resource_name = resource_name
        self.lease_seconds = DISTRIBUTED_READ_LEASE_SECONDS

    # Adds or refreshes this user as an active reader unless a writer owns the DB lock.
    def start_read(self, username: str, server_id: str) -> tuple[bool, str]:
        now = _utc_now()
        expires_at = now + timedelta(seconds=self.lease_seconds)

        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._clear_expired_readers(conn, now)
            writer = self._active_writer(conn, now)
            if writer:
                conn.commit()
                return False, f"Blocked: {writer} owns the distributed write lock."

            existing = self._reader_row(conn, username)
            started_at = existing["started_at"] if existing else _format_dt(now)
            conn.execute(
                "INSERT INTO resource_readers("
                "resource_name, username, owner_server, started_at, last_seen, expires_at"
                ") VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(resource_name, username) DO UPDATE SET "
                "owner_server = excluded.owner_server, "
                "last_seen = excluded.last_seen, "
                "expires_at = excluded.expires_at",
                (
                    self.resource_name,
                    username,
                    server_id,
                    started_at,
                    _format_dt(now),
                    _format_dt(expires_at),
                ),
            )
            conn.commit()
            return True, "Read lock granted. Multiple clients may read concurrently."

    # Refreshes the reader lease while the dashboard is still polling.
    def touch_reader(self, username: str, server_id: str) -> None:
        now = _utc_now()
        expires_at = now + timedelta(seconds=self.lease_seconds)
        with get_connection() as conn:
            conn.execute(
                "UPDATE resource_readers "
                "SET owner_server = ?, last_seen = ?, expires_at = ? "
                "WHERE resource_name = ? AND username = ?",
                (
                    server_id,
                    _format_dt(now),
                    _format_dt(expires_at),
                    self.resource_name,
                    username,
                ),
            )
            conn.commit()

    # Removes the user from the shared active-reader table.
    def finish_read(self, username: str) -> None:
        with get_connection() as conn:
            conn.execute(
                "DELETE FROM resource_readers WHERE resource_name = ? AND username = ?",
                (self.resource_name, username),
            )
            conn.commit()

    def clear_expired_readers_if_needed(self) -> int:
        now = _utc_now()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            removed = self._clear_expired_readers(conn, now)
            conn.commit()
            return removed

    # Returns marker-visible shared reader state for /api/state and the dashboard.
    def current_status(self) -> dict:
        now = _utc_now()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._clear_expired_readers(conn, now)
            rows = conn.execute(
                "SELECT username, owner_server, started_at, last_seen, expires_at "
                "FROM resource_readers WHERE resource_name = ? ORDER BY username",
                (self.resource_name,),
            ).fetchall()
            conn.commit()

        readers = [
            {
                "username": row["username"],
                "owner_server": row["owner_server"],
                "started_at": row["started_at"],
                "last_seen": row["last_seen"],
                "expires_at": row["expires_at"],
            }
            for row in rows
        ]
        return {
            "resource_name": self.resource_name,
            "active_readers": [reader["username"] for reader in readers],
            "reader_count": len(readers),
            "readers": readers,
            "lock_mode": "database-backed distributed reader tracking",
        }

    def _reader_row(self, conn: sqlite3.Connection, username: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT username, started_at FROM resource_readers "
            "WHERE resource_name = ? AND username = ?",
            (self.resource_name, username),
        ).fetchone()

    def _active_writer(self, conn: sqlite3.Connection, now: datetime) -> str | None:
        row = conn.execute(
            "SELECT active_writer, expires_at FROM resource_locks WHERE resource_name = ?",
            (self.resource_name,),
        ).fetchone()
        if not row or not row["active_writer"]:
            return None
        expires_at = _parse_dt(row["expires_at"])
        if expires_at is not None and expires_at <= now:
            return None
        return row["active_writer"]

    def _clear_expired_readers(self, conn: sqlite3.Connection, now: datetime) -> int:
        cursor = conn.execute(
            "DELETE FROM resource_readers WHERE resource_name = ? AND expires_at <= ?",
            (self.resource_name, _format_dt(now)),
        )
        return cursor.rowcount


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


distributed_read_tracker = DistributedReadTracker()
