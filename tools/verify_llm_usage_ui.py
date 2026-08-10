from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest


def main() -> int:
    fixture = ROOT / "tools" / "fixtures" / "llm_usage_ui_app.py"
    app = AppTest.from_file(fixture).run(timeout=30)
    if app.exception:
        print({"ok": False, "exceptions": [str(item.value) for item in app.exception]})
        return 1
    assert len(app.metric) == 4
    assert app.metric[0].label == "总 Token"
    assert app.metric[0].value == "15"
    assert len(app.selectbox) == 2
    print({"ok": True, "checks": 4})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
