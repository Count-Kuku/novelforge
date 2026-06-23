from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import inspect_project_database


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: .\\.venv\\Scripts\\python.exe tools\\inspect_project_db.py <project_name>")
        return 2
    project_name = sys.argv[1]
    result = inspect_project_database(project_name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
