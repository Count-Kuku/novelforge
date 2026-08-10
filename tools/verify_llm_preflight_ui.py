from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest


def main() -> int:
    app = AppTest.from_file(
        ROOT / "tools" / "fixtures" / "llm_preflight_ui_app.py"
    ).run(timeout=30)
    if app.exception:
        print({"ok": False, "exceptions": [str(item.value) for item in app.exception]})
        return 1
    assert [metric.label for metric in app.metric] == [
        "模型调用",
        "输入 Token",
        "输出 Token",
        "总 Token",
        "预计费用",
    ]
    assert app.metric[3].value == "300"
    assert app.metric[4].value == "¥0.0143"
    confirmation_app = AppTest.from_file(
        ROOT / "tools" / "fixtures" / "llm_preflight_confirmation_ui_app.py"
    ).run(timeout=30)
    if confirmation_app.exception:
        print({
            "ok": False,
            "exceptions": [str(item.value) for item in confirmation_app.exception],
        })
        return 1
    assert len(confirmation_app.error) == 1
    assert [item.value for item in confirmation_app.text] == [
        "interactive_result=False",
        "readonly_result=True",
    ]
    print({"ok": True, "checks": 6})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
