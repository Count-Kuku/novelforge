from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui.navigation import ADVANCED_PAGE_GROUPS, PAGE_DESCRIPTIONS


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify() -> None:
    ui_files = sorted((ROOT / "ui").glob("*.py"))
    ui_text = "\n".join(path.read_text(encoding="utf-8") for path in ui_files)
    layout_text = (ROOT / "ui" / "layout.py").read_text(encoding="utf-8")
    common_text = (ROOT / "ui" / "common.py").read_text(encoding="utf-8")

    banned_user_terms = [
        "导演注",
        "地基",
        "流水线",
        "原作对齐",
        "待确认知识",
        "已确认知识",
        "实体卡",
        "世界线",
        "待确认队列",
        "检索资料库",
        "资料索引",
    ]
    for term in banned_user_terms:
        check(term not in ui_text, f"界面文案不再使用“{term}”")

    pages = {page for group_pages in ADVANCED_PAGE_GROUPS.values() for page in group_pages}
    check(pages <= PAGE_DESCRIPTIONS.keys(), "每个导航页面都有说明")
    check(
        all(str(PAGE_DESCRIPTIONS.get(page, "")).strip() for page in pages),
        "每个导航页面说明都不是空文本",
    )

    check('[data-testid="stColumn"]' in layout_text, "对齐样式使用当前 Streamlit 列选择器")
    check('[data-testid="column"]' not in layout_text, "不再使用失效的旧列选择器")
    check("overflow-x: auto !important;" in layout_text, "窄屏标签栏支持横向滚动")
    check("打开：{label}" in common_text, "快捷入口按钮说明目标页面")


def main() -> int:
    try:
        verify()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
