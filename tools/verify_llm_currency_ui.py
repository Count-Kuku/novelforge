from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest


def main() -> int:
    app = AppTest.from_file(
        ROOT / "tools" / "fixtures" / "llm_currency_settings_ui_app.py"
    ).run(timeout=30)
    if app.exception:
        print({"ok": False, "exceptions": [str(item.value) for item in app.exception]})
        return 1
    selectboxes = {item.label: item for item in app.selectbox}
    number_inputs = {item.label: item for item in app.number_input}
    assert selectboxes["价格币种"].value == "CNY"
    assert selectboxes["主显示币种"].value == "CNY"
    assert number_inputs["美元兑人民币换算系数"].value == 7.142857
    assert number_inputs["输入价格 / 百万 Token（CNY）"].value == 1.0
    assert number_inputs["费用提醒阈值（人民币）"].value == 0.5
    print({"ok": True, "checks": 5})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
