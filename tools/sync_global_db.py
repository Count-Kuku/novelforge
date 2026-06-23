from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import inspect_global_database, sync_global_database_from_files


def main() -> int:
    sync_result = sync_global_database_from_files()
    health = inspect_global_database()
    print(json.dumps({
        "sync": sync_result,
        "health": health,
    }, ensure_ascii=False, indent=2))
    return 0 if sync_result.get("ok") and health.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
