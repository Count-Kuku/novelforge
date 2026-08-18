"""验证四入口导航、旧页面迁移和 Streamlit Hub 渲染。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory import create_project, set_active_project_name
from tools.verify_utils import isolated_workspace
from ui.navigation import (
    LEGACY_NAVIGATION_TARGETS,
    TOP_LEVEL_PAGES,
    build_navigation_intent,
    page_groups_for_story,
)
from ui.common import scoped_widget_key


def _assert_no_exception(app: AppTest, label: str) -> None:
    errors = [str(item.value) for item in app.exception]
    if errors:
        raise AssertionError(f"{label} 渲染失败：{errors}")


def _check_pure_contract() -> list[str]:
    checks: list[str] = []
    if TOP_LEVEL_PAGES != ["工作台", "创作", "资料库", "设置"]:
        raise AssertionError(f"顶层导航不符合目标：{TOP_LEVEL_PAGES}")
    checks.append("顶层导航固定为工作台、创作、资料库、设置")

    normal_groups = page_groups_for_story(project_name="demo", planning_pages=[])
    if list(normal_groups) != TOP_LEVEL_PAGES or any(list(value) != [key] for key, value in normal_groups.items()):
        raise AssertionError(f"普通导航分组不是四个单入口：{normal_groups}")
    checks.append("普通导航每个入口只对应一个 Hub")

    expected_pages = set(LEGACY_NAVIGATION_TARGETS)
    for legacy_page in sorted(expected_pages):
        intent = build_navigation_intent(legacy_page)
        if intent.get("page") not in TOP_LEVEL_PAGES:
            raise AssertionError(f"旧页面没有迁移到顶层入口：{legacy_page} -> {intent}")
    checks.append(f"全部 {len(expected_pages)} 个旧页面都有 Hub 迁移目标")

    retrieval_normal = build_navigation_intent("检索中心")
    retrieval_developer = build_navigation_intent("检索中心", developer_mode=True)
    if retrieval_normal.get("page") != "资料库":
        raise AssertionError(f"普通模式检索中心没有回退到资料库：{retrieval_normal}")
    if retrieval_developer.get("page") != "设置":
        raise AssertionError(f"开发者模式检索中心没有进入设置开发工具：{retrieval_developer}")
    checks.append("检索诊断按模式回退或进入开发工具")
    return checks


def _render_legacy_routes() -> list[str]:
    rendered: list[str] = []
    old_routes = [
        "项目总览",
        "项目资源",
        "资料导入",
        "知识库",
        "优先设定",
        "待审核知识",
        "检索中心",
        "创作配置",
        "生成大纲",
        "分卷大纲",
        "剧情段大纲",
        "生成细纲",
        "自由创作",
        "正文生成",
        "章节审阅",
        "模型配置",
        "生成规则",
        "提示词选项",
    ]
    with isolated_workspace("novelforge_navigation_contract_"):
        project_name = create_project("四入口导航验收")
        set_active_project_name(project_name)
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.session_state["project_name"] = project_name
        app.session_state["active_story_id"] = "default"
        app.run(timeout=30)
        _assert_no_exception(app, "初始工作台")

        for old_route in old_routes:
            app.session_state["pending_nav_page"] = old_route
            app.run(timeout=30)
            _assert_no_exception(app, old_route)
            target = build_navigation_intent(old_route)
            actual_page = app.session_state["active_page"] if "active_page" in app.session_state else None
            if actual_page != target.get("page"):
                raise AssertionError(
                    f"{old_route} 没有落到目标 Hub：实际={actual_page} 目标={target}"
                )
            rendered.append(old_route)
    return rendered


def _render_developer_retrieval() -> str:
    previous = os.environ.get("NOVELFORGE_DEVELOPER_MODE")
    os.environ["NOVELFORGE_DEVELOPER_MODE"] = "1"
    try:
        with isolated_workspace("novelforge_navigation_developer_"):
            project_name = create_project("开发工具导航验收")
            set_active_project_name(project_name)
            app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
            app.session_state["project_name"] = project_name
            app.session_state["active_story_id"] = "default"
            app.session_state["pending_nav_page"] = "检索中心"
            app.run(timeout=30)
            _assert_no_exception(app, "开发者资料检索")
            actual_page = app.session_state["active_page"] if "active_page" in app.session_state else None
            if actual_page != "设置":
                raise AssertionError("开发者资料检索没有进入设置 Hub")
    finally:
        if previous is None:
            os.environ.pop("NOVELFORGE_DEVELOPER_MODE", None)
        else:
            os.environ["NOVELFORGE_DEVELOPER_MODE"] = previous
    return "开发者模式资料检索"


def _check_scope_isolation() -> str:
    project_a = scoped_widget_key("creation_hub_view", "project-a", "story-a")
    project_b = scoped_widget_key("creation_hub_view", "project-a", "story-b")
    other_project = scoped_widget_key("creation_hub_view", "project-b", "story-a")
    if len({project_a, project_b, other_project}) != 3:
        raise AssertionError("Hub 状态键没有按项目/故事隔离")
    return "Hub 状态键按项目和故事隔离"


def _render_no_project_settings() -> str:
    with isolated_workspace("novelforge_navigation_no_project_"):
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30)
        app.run(timeout=30)
        _assert_no_exception(app, "无项目设置页")
        actual_page = app.session_state["active_page"] if "active_page" in app.session_state else None
        if actual_page != "设置":
            raise AssertionError(f"无项目时未停留在设置：{actual_page}")
        app.session_state["pending_nav_page"] = "生成规则"
        app.run(timeout=30)
        _assert_no_exception(app, "无项目高级设置迁移")
        if "settings_hub_view" not in app.session_state or app.session_state["settings_hub_view"] != "高级创作":
            raise AssertionError("无项目旧的生成规则入口没有迁移到高级创作设置")
    return "无项目只开放设置入口"


def main() -> int:
    checks: list[str] = []
    try:
        checks.extend(_check_pure_contract())
        rendered = _render_legacy_routes()
        checks.append(f"Streamlit 成功渲染 {len(rendered)} 个旧路由迁移场景")
        checks.append(_render_developer_retrieval())
        checks.append(_check_scope_isolation())
        checks.append(_render_no_project_settings())
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": checks, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": checks}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
