from pathlib import Path

# Data layer paths. Kept server-side as required by the scenario.
BASE_DIR = Path(__file__).resolve().parent.parent
APP_DIR = BASE_DIR / "app"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "users.db"
PRODUCT_FILE_PATH = DATA_DIR / "ProductSpecification.txt"
BACKUP_DIR = DATA_DIR / "backup"

# The simple coursework credential set requested.
DEFAULT_USERS = {
    "Ali": "pass123",
    "Omar": "pass123",
    "Uthman": "pass123",
    "Abu Bakr": "pass123",
    "Talha": "pass123",
    "Zaid": "pass123",
}
