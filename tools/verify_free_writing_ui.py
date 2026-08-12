from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE = ROOT / "ui" / "free_writing"
CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def _function_source(path: Path, name: str) -> str:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    node = next(
        item
        for item in tree.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def verify() -> None:
    expected = {
        "__init__.py",
        "chapter_panel.py",
        "attachments.py",
        "composer.py",
        "fragments.py",
        "knowledge_panel.py",
        "page.py",
        "session_controls.py",
        "shared.py",
    }
    actual = {path.name for path in PACKAGE.glob("*.py")}
    check(expected <= actual, "自由创作页按职责拆分为独立组件")

    entrypoint = ROOT / "ui" / "dynamic_generation.py"
    check(
        len(entrypoint.read_text(encoding="utf-8").splitlines()) <= 10,
        "旧入口只保留兼容转发",
    )
    oversized = {
        path.name: len(path.read_text(encoding="utf-8").splitlines())
        for path in PACKAGE.glob("*.py")
        if len(path.read_text(encoding="utf-8").splitlines()) > 450
    }
    check(not oversized, f"自由创作组件保持可审查大小：{oversized}")

    page_source = _function_source(PACKAGE / "page.py", "render_dynamic_generation_page")
    page_order = [
        page_source.index("render_session_toolbar"),
        page_source.index("render_fragment_history"),
        page_source.index("render_fragment_actions"),
        page_source.index("render_composer"),
        page_source.index("render_knowledge_panel"),
        page_source.index("render_chapter_panel"),
        page_source.index("render_last_context"),
    ]
    check(page_order == sorted(page_order), "主流程按内容、操作、输入、辅助面板排序")

    composer_source = _function_source(PACKAGE / "composer.py", "render_composer")
    check(
        composer_source.index("user_message = st.text_area")
        < composer_source.index("config = _render_advanced_settings"),
        "主输入框显示在高级设置之前",
    )
    check(
        'type="primary"' in composer_source,
        "生成片段保留明确的主操作样式",
    )
    layout_source = (ROOT / "ui" / "layout.py").read_text(encoding="utf-8")
    check(
        'button[kind="primary"]:disabled' in layout_source
        and 'background: #eef1f5 !important;' in layout_source,
        "不可用的主按钮使用中性禁用态",
    )
    settings_source = _function_source(
        PACKAGE / "composer.py",
        "_render_advanced_settings",
    )
    check(
        "compact=True" in settings_source
        and "show_inline_tools=False" in settings_source,
        "高级设置只选择写作偏好，不嵌入完整配置界面",
    )

    package_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(PACKAGE.glob("*.py"))
    )
    for term in (
        "接受当前片段",
        "本轮操作",
        "分支起点",
        "本会话待审核设定",
        "创作提醒（临时要求）",
        "准备整理到第几章",
    ):
        check(term not in package_text, f"自由创作页不再展示旧术语“{term}”")
    for term in (
        "创作记录",
        "保留这段",
        "重写这段",
        "继续写",
        "整理成章节",
        "高级设置",
    ):
        check(term in package_text, f"自由创作页提供直观操作“{term}”")

    check(
        "render_context_directive_tools" not in package_text,
        "自由创作页不再提供重复的临时要求入口",
    )
    session_text = (PACKAGE / "session_controls.py").read_text(encoding="utf-8")
    check(
        '"auto_extract_mode": str(session.get("auto_extract_mode") or "on_accept")'
        in session_text,
        "新创作默认自动整理候选设定",
    )
    _verify_existing_session_render()


def _verify_existing_session_render() -> None:
    from streamlit.testing.v1 import AppTest

    from novelforge.services.memory import create_project, create_story
    from novelforge.workflows import interactive_writing
    from tools.verify_utils import isolated_workspace

    with isolated_workspace("novelforge_free_writing_ui_"):
        project_name = "free_writing_ui_verify"
        create_project(project_name)
        story = create_story(project_name, "界面验证故事")
        story_id = str(story["story_id"])
        session = interactive_writing.create_writing_session(
            project_name,
            story_id,
            session_goal="验证已有自由创作界面",
            writing_guidance={},
            auto_extract_mode="manual",
        )
        session_id = str(session["session_id"])
        with patch.object(
            interactive_writing,
            "call_llm",
            return_value="雨声压低了街巷的回音，她在灯下停住脚步。",
        ):
            interactive_writing.generate_writing_fragment(
                project_name,
                story_id,
                session_id,
                "写一个雨夜相遇的开场",
                action_type="generate",
            )

        source = f'''\
import streamlit as st
from ui.free_writing import render_dynamic_generation_page
from ui.free_writing.shared import active_session_key

st.session_state.setdefault("active_story_id", {story_id!r})
st.session_state.setdefault(active_session_key({project_name!r}, {story_id!r}), {session_id!r})

def render_prompt_options(*_args, **_kwargs):
    return []

render_dynamic_generation_page({project_name!r}, render_prompt_options)
'''
        app = AppTest.from_string(source, default_timeout=30).run()
        exceptions = [str(item.value) for item in app.exception]
        check(not exceptions, f"已有创作状态可以完整渲染：{exceptions}")
        button_labels = {str(item.label) for item in app.button}
        text_area_labels = {str(item.label) for item in app.text_area}
        check("保留这段" in button_labels, "当前片段提供保留操作")
        check("重写这段" in button_labels, "当前片段提供重写操作")
        check("接下来想怎么写？" in text_area_labels, "当前片段后紧接下一轮输入")


def main() -> int:
    try:
        verify()
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "checks": CHECKS, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
