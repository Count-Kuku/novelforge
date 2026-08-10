from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest
from ui.llm_usage import _recent_table


def main() -> int:
    fixture = ROOT / "tools" / "fixtures" / "llm_usage_ui_app.py"
    app = AppTest.from_file(fixture).run(timeout=30)
    if app.exception:
        print({"ok": False, "exceptions": [str(item.value) for item in app.exception]})
        return 1
    assert len(app.metric) == 4
    assert app.metric[0].label == "总 Token"
    assert app.metric[0].value == "15"
    assert app.metric[2].value == "≈¥0.007143"
    assert len(app.selectbox) == 2
    recent = _recent_table(
        [{
            "occurred_at": "2026-08-10T00:00:00+00:00",
            "cost_usd": 0.001,
            "price_snapshot": {"usd_to_cny_rate": 9},
        }],
        {"display_currency": "CNY", "usd_to_cny_rate": 2},
    )
    assert recent[0]["费用（CNY）"] == "0.009000"
    assert recent[0]["费用（USD）"] == "0.001000"
    print({"ok": True, "checks": 7})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
