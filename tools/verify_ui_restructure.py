"""四入口 UI 重构验收：源码契约、Hub 子视图和旧路由迁移。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory import create_project, set_active_project_name
from tools.verify_navigation_contract import _assert_no_exception, _render_developer_retrieval, _render_legacy_routes
from tools.verify_utils import isolated_workspace
from ui.common import scoped_widget_key
from ui.navigation import LEGACY_PAGE_GROUPS, PAGE_DESCRIPTIONS, TOP_LEVEL_PAGES


def _source_checks() -> list[str]:
    checks: list[str] = []
    all_legacy_pages = {page for pages in LEGACY_PAGE_GROUPS.values() for page in pages}
    missing_descriptions = sorted(page for page in all_legacy_pages if not str(PAGE_DESCRIPTIONS.get(page) or "").strip())
    if missing_descriptions:
        raise AssertionError(f"旧页面缺少迁移说明：{missing_descriptions}")
    checks.append("全部旧页面仍有可读迁移说明")

    if list(TOP_LEVEL_PAGES) != ["工作台", "创作", "资料库", "设置"]:
        raise AssertionError(f"普通导航不是四个固定入口：{TOP_LEVEL_PAGES}")
    checks.append("普通导航固定为四个顶层 Hub")

    ingestion_source = (ROOT / "ui" / "retrieval_ingestion_page.py").read_text(encoding="utf-8")
    for label in ["概览", "导入", "处理", "管理"]:
        if label not in ingestion_source:
            raise AssertionError(f"资料导入缺少工作区：{label}")
    checks.append("资料导入保留概览、导入、处理和管理工作区")

    hub_files = [
        ROOT / "ui" / "workbench_hub.py",
        ROOT / "ui" / "creation_hub.py",
        ROOT / "ui" / "library_hub.py",
        ROOT / "ui" / "settings_hub.py",
    ]
    missing_hubs = [str(path.relative_to(ROOT)) for path in hub_files if not path.exists()]
    if missing_hubs:
        raise AssertionError(f"缺少 Hub 文件：{missing_hubs}")
    checks.append("四个 Hub 文件均存在")

    legacy_width_files = []
    for path in list((ROOT / "ui").rglob("*.py")) + [ROOT / "app.py"]:
        if "use_container_width" in path.read_text(encoding="utf-8"):
            legacy_width_files.append(str(path.relative_to(ROOT)))
    if legacy_width_files:
        raise AssertionError(f"仍使用过期宽度参数：{legacy_width_files}")
    checks.append("全部界面组件使用统一的新宽度 API")

    layout_text = (ROOT / "ui" / "layout.py").read_text(encoding="utf-8")
    if '[data-testid="stColumn"]' not in layout_text or '[data-testid="column"]' in layout_text:
        raise AssertionError("列布局选择器没有使用当前 Streamlit API")
    checks.append("列布局选择器和窄屏样式保持有效")
    return checks


def _render_hub_views() -> list[str]:
    rendered: list[str] = []
    with isolated_workspace("novelforge_hub_views_"):
        project_name = create_project("四入口 Hub 验收")
        set_active_project_name(project_name)
        story_id = "default"
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.session_state["project_name"] = project_name
        app.session_state["active_story_id"] = story_id
        app.run(timeout=30)
        _assert_no_exception(app, "Hub 初始页面")

        workbench_key = scoped_widget_key("workbench_hub_view", project_name, story_id)
        for value in ["概览", "内容", "项目与故事"]:
            app.session_state["pending_nav_page"] = "工作台"
            app.session_state[workbench_key] = value
            app.run(timeout=30)
            _assert_no_exception(app, f"工作台 / {value}")
            rendered.append(f"工作台 / {value}")

        creation_key = scoped_widget_key("creation_hub_view", project_name, story_id)
        planning_key = scoped_widget_key("creation_planning_view", project_name, story_id)
        for value in ["创作方向", "自由模式", "章节写作"]:
            app.session_state["pending_nav_page"] = "创作"
            app.session_state[creation_key] = value
            app.run(timeout=30)
            _assert_no_exception(app, f"创作 / {value}")
            rendered.append(f"创作 / {value}")
        for planning_view in ["全书", "分卷", "剧情段", "章节细纲"]:
            app.session_state["pending_nav_page"] = "创作"
            app.session_state[creation_key] = "小说规划"
            app.session_state[planning_key] = planning_view
            app.run(timeout=30)
            _assert_no_exception(app, f"创作 / 小说规划 / {planning_view}")
            rendered.append(f"创作 / 小说规划 / {planning_view}")

        library_key = scoped_widget_key("library_hub_view", project_name, story_id)
        for value in ["查找与编辑", "优先设定", "待审核", "导入与来源"]:
            app.session_state["pending_nav_page"] = "资料库"
            app.session_state[library_key] = value
            app.run(timeout=30)
            _assert_no_exception(app, f"资料库 / {value}")
            rendered.append(f"资料库 / {value}")

        for value in ["模型与费用", "高级创作"]:
            app.session_state["pending_nav_page"] = "设置"
            app.session_state["settings_hub_view"] = value
            app.run(timeout=30)
            _assert_no_exception(app, f"设置 / {value}")
            rendered.append(f"设置 / {value}")
    return rendered


def main() -> int:
    checks: list[str] = []
    try:
        checks.extend(_source_checks())
        checks.append(f"Hub 子视图渲染通过：{len(_render_hub_views())} 个")
        checks.append(f"旧路由迁移渲染通过：{len(_render_legacy_routes())} 个")
        checks.append(_render_developer_retrieval())
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": checks, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
