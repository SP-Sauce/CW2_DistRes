from .config import PRODUCT_FILE_PATH
from .replication_service import replication_service
from .rw_lock import rw_coordinator


class ResourceAccessService:
    
    # Logical microservice: ResourceAccessService.

    # Rubric/design link:
    # - Provides client access to the distributed shared resource.
    # - Uses the ReadWriteCoordinator before reading/writing ProductSpecification.txt.
    # - Keeps file operations inside the data/resource layer instead of directly in routes.
    

    def start_read(self, username: str) -> tuple[bool, str, str]:
        granted, message = rw_coordinator.start_read(username)
        if not granted:
            return False, message, ""
        return True, message, PRODUCT_FILE_PATH.read_text(encoding="utf-8")

    def finish_read(self, username: str) -> None:
        rw_coordinator.finish_read(username)

    def request_write(self, username: str) -> tuple[str, str, str]:
        status, message = rw_coordinator.request_write(username)
        content = PRODUCT_FILE_PATH.read_text(encoding="utf-8") if status in {"GRANTED", "ACTIVE"} else ""
        return status, message, content

    def save_write(self, username: str, new_content: str) -> tuple[bool, str]:
        lock_state = rw_coordinator.status()
        if lock_state["active_writer"] != username:
            return False, "Save rejected: you do not currently own the write lock."

        PRODUCT_FILE_PATH.write_text(new_content, encoding="utf-8")
        replication_service.snapshot()
        return True, "File updated and replicated to backup snapshot."

    def finish_write(self, username: str) -> bool:
        return rw_coordinator.finish_write(username)

    def status(self) -> dict:
        return rw_coordinator.status()


resource_service = ResourceAccessService()
