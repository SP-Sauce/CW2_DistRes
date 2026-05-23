import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import BACKUP_DIR, DB_PATH, PRODUCT_FILE_PATH


class ReplicationService:
    
    # Logical microservice: Replication / Sync Service.

    # Rubric/design link:
    # - Mirrors the diagram's backup data store using simple file snapshots.
    # - Keeps a replica of the DB and ProductSpecification file after updates.
    # - Demonstrates the reliability/fault-tolerance idea without needing paid cloud infra.
    

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
