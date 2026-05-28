from pathlib import Path
import os
import runpy
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]


def main() -> None:
    os.chdir(ROOT_DIR)
    sys.path.insert(0, str(ROOT_DIR))

    os.environ["DISTRES_NODE1_URL"] = "http://127.0.0.1:8001"
    os.environ["DISTRES_NODE2_URL"] = "http://127.0.0.1:8002"
    os.environ["DISTRES_NODE3_URL"] = "http://127.0.0.1:8003"
    os.environ["PORT"] = "8000"

    runpy.run_path(str(ROOT_DIR / "gateway.py"), run_name="__main__")


if __name__ == "__main__":
    main()
