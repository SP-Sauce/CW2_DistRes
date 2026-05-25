from .config import PRODUCT_FILE_PATH
from .replication_service import replication_service
from .rw_lock import rw_coordinator


# Logical service that controls read/write access to the shared product file.
class ResourceAccessService:
    # Tries to grant read access and returns the current file content if allowed.
    def start_read(self, username: str) -> tuple[bool, str, str]:
        granted, message = rw_coordinator.start_read(username)
        if not granted:
            return False, message, ""
        return True, message, PRODUCT_FILE_PATH.read_text(encoding="utf-8")

    # Releases a user's read lock after they finish viewing the shared file.
    def finish_read(self, username: str) -> None:
        rw_coordinator.finish_read(username)

    # Tries to grant or queue write access and returns editable content if granted.
    def request_write(self, username: str) -> tuple[str, str, str]:
        status, message = rw_coordinator.request_write(username)
        content = PRODUCT_FILE_PATH.read_text(encoding="utf-8") if status in {"GRANTED", "ACTIVE"} else ""
        return status, message, content

    # Writes new content only if the user currently owns the write lock.
    def save_write(self, username: str, new_content: str) -> tuple[bool, str]:
        lock_state = rw_coordinator.status()
        if lock_state["active_writer"] != username:
            return False, "Save rejected: you do not currently own the write lock."

        PRODUCT_FILE_PATH.write_text(new_content, encoding="utf-8")
        replication = replication_service.replicate_state(product_content=new_content)
        if replication["ok"]:
            return True, "File updated and replicated to the standby replica."
        return True, "File updated locally with a backup snapshot; standby replication will need retry."

    # Releases a user's write lock so the next queued writer can continue.
    def finish_write(self, username: str) -> bool:
        return rw_coordinator.finish_write(username)

    # Returns the current read/write lock state for the dashboard.
    def status(self) -> dict:
        return rw_coordinator.status()


resource_service = ResourceAccessService()
