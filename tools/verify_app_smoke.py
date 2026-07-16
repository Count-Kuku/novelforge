from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest

from tools.verify_utils import isolated_workspace


def main() -> int:
    with isolated_workspace("novelforge_app_smoke_"):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        exceptions = [str(item.value) for item in app.exception]
        result = {
            "ok": not exceptions,
            "exceptions": exceptions,
            "titles": [str(item.value) for item in app.title],
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
