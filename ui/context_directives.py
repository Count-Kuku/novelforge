"""Shared UI for project/story/chapter/run-scoped generation directives."""
from __future__ import annotations

import streamlit as st

from novelforge.services.memory import (
    delete_context_directive,
    load_context_directives,
    save_context_directive,
)
from ui.common import scoped_widget_key


SCOPE_LABELS = {
    "run": "仅下一次成功生成",
    "chapter": "当前章节",
    "story": "当前故事",
    "project": "整个项目",
}
PLACEMENT_LABELS = {
    "hard_constraints": "必须遵守",
    "story_state": "当前剧情状态",
    "chapter_direction": "本章写作方向",
    "character_voice": "人物说话方式",
    "style": "文风与表达",
    "reference": "资料使用重点",
}


def _directive_summary(directive: dict) -> str:
    enabled = "生效" if directive.get("enabled", True) else "停用"
    scope = SCOPE_LABELS.get(str(directive.get("scope") or ""), str(directive.get("scope") or ""))
    placement = PLACEMENT_LABELS.get(
        str(directive.get("placement") or ""),
        str(directive.get("placement") or ""),
    )
    remaining = directive.get("remaining_uses")
    remaining_text = "不限次数" if remaining is None else f"剩余 {remaining} 次"
    return f"{enabled} · {scope} · {placement} · {remaining_text} · 优先级 {directive.get('priority', 50)}"


def _render_existing_directives(project_name: str, story_id: str, capability: str, chapter_no: int | None) -> None:
    directives = load_context_directives(project_name, story_id)
    if not directives:
        st.caption("当前没有创作提醒。需要临时强调视角、节奏或禁写内容时，可以在下方添加。")
        return

    for directive in directives:
        directive_id = str(directive.get("directive_id") or "")
        capabilities = [str(value) for value in directive.get("capabilities", []) if str(value)]
        if capabilities and capability not in capabilities:
            continue
        scope = str(directive.get("scope") or "story")
        if scope == "chapter" and chapter_no is not None:
            start = directive.get("chapter_start")
            end = directive.get("chapter_end")
            if (start is not None and chapter_no < int(start)) or (end is not None and chapter_no > int(end)):
                continue
        with st.container(border=True):
            st.markdown(f"**{directive.get('name') or '未命名创作提醒'}**")
            st.caption(_directive_summary(directive))
            st.write(str(directive.get("content") or ""))
            toggle_col, delete_col = st.columns(2)
            toggle_label = "停用" if directive.get("enabled", True) else "启用"
            if toggle_col.button(
                toggle_label,
                key=scoped_widget_key("directive_toggle", project_name, story_id, directive_id),
                use_container_width=True,
            ):
                updated = dict(directive)
                updated["enabled"] = not bool(directive.get("enabled", True))
                if updated["enabled"] and updated.get("remaining_uses") == 0:
                    updated["remaining_uses"] = 1
                save_context_directive(
                    project_name,
                    updated,
                    story_id=directive.get("story_id"),
                )
                st.rerun()
            if delete_col.button(
                "删除",
                key=scoped_widget_key("directive_delete", project_name, story_id, directive_id),
                use_container_width=True,
            ):
                delete_context_directive(project_name, directive_id, story_id=story_id)
                st.rerun()


def render_context_directive_tools(
    project_name: str,
    story_id: str,
    *,
    capability: str,
    chapter_no: int | None = None,
) -> None:
    with st.expander("创作提醒（临时要求）", expanded=False):
        st.caption(
            "用于临时告诉模型这一轮该怎么写，例如限定视角、节奏或禁写内容。"
            "它不会自动变成世界观设定；选择“仅下一次”时，只在内容成功生成并保存后使用一次。"
        )
        _render_existing_directives(project_name, story_id, capability, chapter_no)

        st.markdown("#### 新增创作提醒")
        form_key = scoped_widget_key(
            "directive_create",
            project_name,
            story_id,
            capability,
            chapter_no if chapter_no is not None else "none",
        )
        with st.form(form_key, clear_on_submit=True):
            name = st.text_input("提醒名称", placeholder="例如：本章保持克制视角")
            content = st.text_area(
                "具体要求",
                height=110,
                placeholder="例如：本章只使用林黛玉视角，不进入其他人物内心。",
            )
            scope_col, type_col = st.columns(2)
            scope = scope_col.selectbox(
                "在哪些生成中生效",
                options=list(SCOPE_LABELS),
                format_func=lambda value: SCOPE_LABELS[value],
            )
            placement = type_col.selectbox(
                "提醒类型",
                options=list(PLACEMENT_LABELS),
                index=list(PLACEMENT_LABELS).index("chapter_direction"),
                format_func=lambda value: PLACEMENT_LABELS[value],
            )
            priority = st.slider("优先级", min_value=0, max_value=100, value=70)
            remaining_uses = st.number_input(
                "最多生效几次（0 表示不限）",
                min_value=0,
                max_value=100,
                value=1 if scope == "run" else 0,
            )
            submitted = st.form_submit_button("保存创作提醒", use_container_width=True)
        if submitted:
            if not content.strip():
                st.error("请填写具体要求。")
                return
            resolved_scope = str(scope)
            payload = {
                "name": name.strip() or content.strip().splitlines()[0][:48],
                "content": content.strip(),
                "scope": resolved_scope,
                "story_id": None if resolved_scope == "project" else story_id,
                "chapter_start": chapter_no if resolved_scope == "chapter" and chapter_no is not None else None,
                "chapter_end": chapter_no if resolved_scope == "chapter" and chapter_no is not None else None,
                "capabilities": [capability],
                "placement": placement,
                "priority": int(priority),
                "enabled": True,
                "remaining_uses": 1 if resolved_scope == "run" else (int(remaining_uses) or None),
            }
            try:
                save_context_directive(
                    project_name,
                    payload,
                    story_id=None if resolved_scope == "project" else story_id,
                )
                st.success("创作提醒已保存。")
                st.rerun()
            except Exception as exc:
                st.error(f"创作提醒保存失败：{exc}")
