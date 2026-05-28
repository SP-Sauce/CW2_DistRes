import os
from pathlib import Path

# Data layer paths. Kept server-side as required by the scenario.
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

_data_dir = os.environ.get("DISTRES_DATA_DIR")
_backup_dir = os.environ.get("DISTRES_BACKUP_DIR")
DATA_DIR = Path(_data_dir).resolve() if _data_dir else BASE_DIR / "data"
DB_PATH = DATA_DIR / "users.db"
PRODUCT_FILE_PATH = DATA_DIR / "ProductSpecification.txt"
BACKUP_DIR = Path(_backup_dir).resolve() if _backup_dir else BASE_DIR / "data" / "backup"

# Model A node settings. Every node can serve safe reads; the gateway routes writes to leader.
NODE_ID = os.environ.get("DISTRES_NODE_ID", "local")
REPLICATION_TARGET = os.environ.get("DISTRES_REPLICATION_TARGET", "").rstrip("/")
SESSION_STALE_AFTER_SECONDS = int(os.environ.get("DISTRES_SESSION_STALE_AFTER_SECONDS", "60"))
DISTRIBUTED_LOCK_LEASE_SECONDS = int(
    os.environ.get("DISTRIBUTED_LOCK_LEASE_SECONDS", "60")
)
DISTRIBUTED_READ_LEASE_SECONDS = int(
    os.environ.get("DISTRIBUTED_READ_LEASE_SECONDS", "120")
)

# The simple coursework credential set requested.
DEFAULT_USERS = {
    "Ali": "pass123",
    "Omar": "pass123",
    "Uthman": "pass123",
    "Abu Bakr": "pass123",
    "Talha": "pass123",
    "Zaid": "pass123",
}
