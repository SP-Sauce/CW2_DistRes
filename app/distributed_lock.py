import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import DISTRIBUTED_LOCK_LEASE_SECONDS, DISTRIBUTED_WRITE_WAIT_LEASE_SECONDS
from .database import get_connection


RESOURCE_NAME = "ProductSpecification.txt"


class DistributedWriteLock:
    # SQLite-backed final guard for leader-routed writes.
    def __init__(self, resource_name: str = RESOURCE_NAME) -> None:
        self.resource_name = resource_name
        self.lease_seconds = DISTRIBUTED_LOCK_LEASE_SECONDS
        self.wait_lease_seconds = DISTRIBUTED_WRITE_WAIT_LEASE_SECONDS

    # Atomically grants the write lease if the resource is free or the old lease expired.
    def request_write(self, username: str, server_id: str) -> tuple[str, str, str | None]:
        now = _utc_now()
        expires_at = now + timedelta(seconds=self.lease_seconds)
        waiter_expires_at = now + timedelta(seconds=self.wait_lease_seconds)

        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._clear_expired_waiters(conn, now)
            row = self._lock_row(conn)
            if self._is_expired(row, now):
                self._clear_lock(conn)
                row = self._lock_row(conn)

            if row["active_writer"] == username:
                self._remove_waiter(conn, username)
                conn.commit()
                return (
                    "ACTIVE",
                    "You already own the database-backed distributed write lock.",
                    row["lock_token"],
                )

            if row["active_writer"]:
                self._upsert_waiter(
                    conn,
                    username,
                    server_id,
                    now,
                    waiter_expires_at,
                    f"Waiting for {row['active_writer']} to release the write lock.",
                )
                conn.commit()
                return (
                    "WAITING",
                    f"Blocked: {row['active_writer']} owns the distributed write lock.",
                    None,
                )

            self._clear_expired_readers(conn, now)
            active_readers = self._active_readers(conn, username)
            if active_readers:
                self._upsert_waiter(
                    conn,
                    username,
                    server_id,
                    now,
                    waiter_expires_at,
                    f"Waiting for active readers: {', '.join(active_readers)}.",
                )
                conn.commit()
                return (
                    "WAITING",
                    f"Blocked: active readers are still reading: {', '.join(active_readers)}.",
                    None,
                )

            waiters = self._waiting_rows(conn)
            if waiters and waiters[0]["username"] != username:
                first_waiter = waiters[0]["username"]
                self._upsert_waiter(
                    conn,
                    username,
                    server_id,
                    now,
                    waiter_expires_at,
                    f"Waiting behind {first_waiter} in the write queue.",
                )
                conn.commit()
                return (
                    "WAITING",
                    f"Blocked: {first_waiter} is first in the distributed write queue.",
                    None,
                )

            lock_token = secrets.token_urlsafe(24)
            conn.execute(
                "UPDATE resource_locks "
                "SET active_writer = ?, lock_token = ?, owner_server = ?, "
                "acquired_at = ?, expires_at = ?, version = version + 1 "
                "WHERE resource_name = ?",
                (
                    username,
                    lock_token,
                    server_id,
                    _format_dt(now),
                    _format_dt(expires_at),
                    self.resource_name,
                ),
            )
            self._remove_waiter(conn, username)
            conn.commit()
            return (
                "GRANTED",
                "Distributed write lock granted by the elected leader.",
                lock_token,
            )

    # Releases the lease only for the current owner, and checks token when supplied.
    def finish_write(self, username: str, lock_token: Optional[str] = None) -> bool:
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._lock_row(conn)
            token_matches = lock_token is None or lock_token == row["lock_token"]
            if row["active_writer"] != username or not token_matches:
                conn.commit()
                return False
            self._clear_lock(conn)
            self._remove_waiter(conn, username)
            conn.commit()
            return True

    # Confirms the current user still owns the unexpired distributed write lease.
    def can_write(self, username: str, lock_token: Optional[str] = None) -> bool:
        now = _utc_now()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._lock_row(conn)
            if self._is_expired(row, now):
                self._clear_lock(conn)
                conn.commit()
                return False

            token_matches = lock_token is None or lock_token == row["lock_token"]
            allowed = row["active_writer"] == username and token_matches
            conn.commit()
            return allowed

    def clear_expired_lock_if_needed(self) -> bool:
        now = _utc_now()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = self._lock_row(conn)
            if not self._is_expired(row, now):
                conn.commit()
                return False
            self._clear_lock(conn)
            conn.commit()
            return True

    # Dashboard/API status for marker-visible evidence of the DB-backed lock.
    def current_status(self) -> dict:
        now = _utc_now()
        with get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._clear_expired_waiters(conn, now)
            row = self._lock_row(conn)
            waiters = self._waiting_rows(conn)
            conn.commit()
        waiting_writers = [
            {
                "username": row["username"],
                "owner_server": row["owner_server"],
                "requested_at": row["requested_at"],
                "last_seen": row["last_seen"],
                "expires_at": row["expires_at"],
                "reason": row["reason"],
            }
            for row in waiters
        ]
        return {
            "resource_name": row["resource_name"],
            "active_writer": row["active_writer"],
            "owner_server": row["owner_server"],
            "acquired_at": row["acquired_at"],
            "expires_at": row["expires_at"],
            "version": row["version"],
            "is_expired": self._is_expired(row, now),
            "waiting_writers": [writer["username"] for writer in waiting_writers],
            "waiting_count": len(waiting_writers),
            "write_waiters": waiting_writers,
            "lock_mode": "database-backed distributed write lock",
        }

    def _lock_row(self, conn: sqlite3.Connection) -> sqlite3.Row:
        row = conn.execute(
            "SELECT resource_name, active_writer, lock_token, owner_server, "
            "acquired_at, expires_at, version "
            "FROM resource_locks WHERE resource_name = ?",
            (self.resource_name,),
        ).fetchone()
        if row:
            return row

        conn.execute(
            "INSERT INTO resource_locks("
            "resource_name, active_writer, lock_token, owner_server, acquired_at, expires_at, version"
            ") VALUES (?, NULL, NULL, NULL, NULL, NULL, 0)",
            (self.resource_name,),
        )
        return conn.execute(
            "SELECT resource_name, active_writer, lock_token, owner_server, "
            "acquired_at, expires_at, version "
            "FROM resource_locks WHERE resource_name = ?",
            (self.resource_name,),
        ).fetchone()

    def _clear_lock(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE resource_locks "
            "SET active_writer = NULL, lock_token = NULL, owner_server = NULL, "
            "acquired_at = NULL, expires_at = NULL, version = version + 1 "
            "WHERE resource_name = ?",
            (self.resource_name,),
        )

    def _active_readers(self, conn: sqlite3.Connection, username: str) -> list[str]:
        rows = conn.execute(
            "SELECT username FROM resource_readers "
            "WHERE resource_name = ? AND username <> ? ORDER BY username",
            (self.resource_name, username),
        ).fetchall()
        return [row["username"] for row in rows]

    def _clear_expired_readers(self, conn: sqlite3.Connection, now: datetime) -> None:
        conn.execute(
            "DELETE FROM resource_readers WHERE resource_name = ? AND expires_at <= ?",
            (self.resource_name, _format_dt(now)),
        )

    def _waiting_rows(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return conn.execute(
            "SELECT username, owner_server, requested_at, last_seen, expires_at, reason "
            "FROM resource_write_waiters WHERE resource_name = ? ORDER BY requested_at",
            (self.resource_name,),
        ).fetchall()

    def _upsert_waiter(
        self,
        conn: sqlite3.Connection,
        username: str,
        server_id: str,
        now: datetime,
        expires_at: datetime,
        reason: str,
    ) -> None:
        existing = conn.execute(
            "SELECT requested_at FROM resource_write_waiters "
            "WHERE resource_name = ? AND username = ?",
            (self.resource_name, username),
        ).fetchone()
        requested_at = existing["requested_at"] if existing else _format_dt(now)
        conn.execute(
            "INSERT INTO resource_write_waiters("
            "resource_name, username, owner_server, requested_at, last_seen, expires_at, reason"
            ") VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(resource_name, username) DO UPDATE SET "
            "owner_server = excluded.owner_server, "
            "last_seen = excluded.last_seen, "
            "expires_at = excluded.expires_at, "
            "reason = excluded.reason",
            (
                self.resource_name,
                username,
                server_id,
                requested_at,
                _format_dt(now),
                _format_dt(expires_at),
                reason,
            ),
        )

    def _remove_waiter(self, conn: sqlite3.Connection, username: str) -> None:
        conn.execute(
            "DELETE FROM resource_write_waiters WHERE resource_name = ? AND username = ?",
            (self.resource_name, username),
        )

    def _clear_expired_waiters(self, conn: sqlite3.Connection, now: datetime) -> None:
        conn.execute(
            "DELETE FROM resource_write_waiters WHERE resource_name = ? AND expires_at <= ?",
            (self.resource_name, _format_dt(now)),
        )

    def _is_expired(self, row: sqlite3.Row, now: datetime) -> bool:
        expires_at = _parse_dt(row["expires_at"])
        return row["active_writer"] is not None and expires_at is not None and expires_at <= now


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _format_dt(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


distributed_write_lock = DistributedWriteLock()
