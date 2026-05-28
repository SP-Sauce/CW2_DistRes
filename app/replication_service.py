import json
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from .config import BACKUP_DIR, DB_PATH, PRODUCT_FILE_PATH, REPLICATION_TARGET


# Keeps backup snapshots and optionally replicates state when a target is configured.
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

    # Sends current state to a configured target over HTTP; Model A normally uses snapshots only.
    def replicate_state(
        self,
        *,
        product_content: str | None = None,
        sessions: list[dict] | None = None,
    ) -> dict[str, Any]:
        snapshot = self.snapshot()
        if not REPLICATION_TARGET:
            return {"ok": True, "mode": "snapshot_only", "snapshot": snapshot}

        payload = {
            "product_content": product_content,
            "sessions": sessions,
            "replicated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            f"{REPLICATION_TARGET}/internal/replicate/state",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                body = response.read().decode("utf-8")
            return {
                "ok": True,
                "mode": "replicated",
                "target": REPLICATION_TARGET,
                "status": getattr(response, "status", 200),
                "response": json.loads(body) if body else {},
                "snapshot": snapshot,
            }
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {
                "ok": False,
                "mode": "replication_failed",
                "target": REPLICATION_TARGET,
                "error": str(exc),
                "snapshot": snapshot,
            }


replication_service = ReplicationService()
