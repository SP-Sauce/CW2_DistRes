from pathlib import Path
import os
import runpy
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    os.chdir(ROOT_DIR)
    sys.path.insert(0, str(ROOT_DIR))

    os.environ["DISTRES_NODE_ID"] = "node2"
    os.environ["DISTRES_DATA_DIR"] = str(ROOT_DIR / "data" / "shared")
    os.environ["DISTRES_BACKUP_DIR"] = str(ROOT_DIR / "data" / "backup")
    os.environ.pop("DISTRES_REPLICATION_TARGET", None)
    os.environ["PORT"] = "8002"

    runpy.run_path(str(ROOT_DIR / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
