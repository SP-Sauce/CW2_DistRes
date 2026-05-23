import shutil
from datetime import datetime, timezone

from .config import BACKUP_DIR, DB_PATH, PRODUCT_FILE_PATH


# Logical replication service that keeps backup snapshots of server-side data.
class ReplicationService:
    # Copies the database and product specification file into the backup store.
    def snapshot(self) -> dict:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        db_backup = BACKUP_DIR / "users.db.snapshot"
        file_backup = BACKUP_DIR / "ProductSpecification.txt.snapshot"

        if DB_PATH.exists():
            shutil.copy2(DB_PATH, db_backup)
        if PRODUCT_FILE_PATH.exists():
            shutil.copy2(PRODUCT_FILE_PATH, file_backup)

        return {
            "snapshot_time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "db_backup": str(db_backup),
            "file_backup": str(file_backup),
        }


replication_service = ReplicationService()
