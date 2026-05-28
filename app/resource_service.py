from .config import NODE_ID, PRODUCT_FILE_PATH
from .distributed_lock import distributed_write_lock
from .distributed_readers import distributed_read_tracker
from .replication_service import replication_service


# Logical service that controls read/write access to the shared product file.
class ResourceAccessService:
    # Tries to grant read access and returns the current file content if allowed.
    def start_read(self, username: str) -> tuple[bool, str, str]:
        granted, message = distributed_read_tracker.start_read(username, NODE_ID)
        if not granted:
            return False, message, ""
        return True, message, PRODUCT_FILE_PATH.read_text(encoding="utf-8")

    # Releases a user's shared read marker after they finish viewing the shared file.
    def finish_read(self, username: str) -> None:
        distributed_read_tracker.finish_read(username)

    # Keeps active readers visible while their dashboard continues polling.
    def touch_read(self, username: str) -> None:
        distributed_read_tracker.touch_reader(username, NODE_ID)

    # Requests the DB-backed distributed write lock from the elected leader.
    def request_write(self, username: str) -> tuple[str, str, str, str | None]:
        # A client moving from read to write should not remain an active reader.
        distributed_read_tracker.finish_read(username)
        status, message, lock_token = distributed_write_lock.request_write(username, NODE_ID)
        content = PRODUCT_FILE_PATH.read_text(encoding="utf-8") if status in {"GRANTED", "ACTIVE"} else ""
        return status, message, content, lock_token

    # Writes new content only when the user owns the DB-backed distributed write lock.
    def save_write(self, username: str, new_content: str, lock_token: str | None = None) -> tuple[bool, str]:
        if not distributed_write_lock.can_write(username, lock_token):
            return False, "Save rejected: you do not own the distributed write lock."

        PRODUCT_FILE_PATH.write_text(new_content, encoding="utf-8")
        replication = replication_service.replicate_state(product_content=new_content)
        if replication["ok"]:
            return True, "File updated through leader-routed write and DB-backed distributed lock."
        return True, "File updated through leader-routed write and DB-backed distributed lock; backup snapshot kept locally."

    # Releases the DB-backed distributed write lock so another client can write.
    def finish_write(self, username: str, lock_token: str | None = None) -> bool:
        return distributed_write_lock.finish_write(username, lock_token)

    # Returns shared reader markers and the distributed write lock state.
    def status(self) -> dict:
        distributed_read_status = distributed_read_tracker.current_status()
        distributed_status = distributed_write_lock.current_status()
        return {
            "active_readers": distributed_read_status["active_readers"],
            "active_writer": distributed_status["active_writer"],
            "waiting_writers": [],
            "read_count": distributed_read_status["reader_count"],
            "distributed_readers": distributed_read_status,
            "distributed_write_lock": distributed_status,
        }


resource_service = ResourceAccessService()
