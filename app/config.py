import os
from pathlib import Path

# Data layer paths. Kept server-side as required by the scenario.
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

_data_dir = os.environ.get("DISTRES_DATA_DIR")
DATA_DIR = Path(_data_dir).resolve() if _data_dir else BASE_DIR / "data"
DB_PATH = DATA_DIR / "users.db"
PRODUCT_FILE_PATH = DATA_DIR / "ProductSpecification.txt"
BACKUP_DIR = DATA_DIR / "backup"

# Real active/passive node settings used when running primary and standby servers.
NODE_ID = os.environ.get("DISTRES_NODE_ID", "local")
NODE_ROLE = os.environ.get("DISTRES_ROLE", "primary").lower()
REPLICATION_TARGET = os.environ.get("DISTRES_REPLICATION_TARGET", "").rstrip("/")

# The simple coursework credential set requested.
DEFAULT_USERS = {
    "Ali": "pass123",
    "Omar": "pass123",
    "Uthman": "pass123",
    "Abu Bakr": "pass123",
    "Talha": "pass123",
    "Zaid": "pass123",
}
