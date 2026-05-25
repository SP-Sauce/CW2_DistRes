from pathlib import Path
import os
import runpy
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    os.chdir(ROOT_DIR)
    sys.path.insert(0, str(ROOT_DIR))

    os.environ["DISTRES_NODE_ID"] = "primary"
    os.environ["DISTRES_ROLE"] = "primary"
    os.environ["DISTRES_DATA_DIR"] = str(ROOT_DIR / "data")
    os.environ["DISTRES_REPLICATION_TARGET"] = "http://127.0.0.1:8002"
    os.environ["PORT"] = "8001"

    runpy.run_path(str(ROOT_DIR / "main.py"), run_name="__main__")


if __name__ == "__main__":
    main()
