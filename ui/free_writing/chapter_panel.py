"""Compile accepted free-writing fragments into a formal chapter."""

from __future__ import annotations

import streamlit as st

from novelforge.workflows.interactive_writing import (
    compile_session_text,
    save_writing_session_as_chapter,
)
from ui.common import scoped_widget_key
from ui.streaming import run_with_stream


def render_chapter_panel(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    compiled = compile_session_text(bundle)
    if not compiled.strip():
        return

    session = dict(bundle.get("session", {}) or {})
    session_id = str(session.get("session_id") or "")
    archived = str(session.get("status") or "") == "archived"
    with st.expander("整理成章节", expanded=False):
        st.caption("这里只包含当前创作中已经保留、且尚未整理进章节的内容。")
        st.text_area(
            "内容预览",
            value=compiled,
            height=320,
            disabled=True,
            key=scoped_widget_key(
                "creative_compile_preview",
                project_name,
                story_id,
                session_id,
            ),
        )
        chapter_no = st.number_input(
            "保存到第几章",
            min_value=1,
            value=int(session.get("target_chapter_no") or 1),
            key=scoped_widget_key(
                "creative_compile_chapter",
                project_name,
                story_id,
                session_id,
            ),
        )
        append_existing = st.checkbox(
            "已有正文时追加到末尾",
            value=False,
            key=scoped_widget_key(
                "creative_compile_append",
                project_name,
                story_id,
                session_id,
            ),
        )
        smooth = st.checkbox(
            "使用模型润色片段衔接",
            value=False,
            key=scoped_widget_key(
                "creative_compile_smooth",
                project_name,
                story_id,
                session_id,
            ),
        )
        if st.button(
            "保存为章节",
            disabled=archived,
            key=scoped_widget_key(
                "creative_compile_save",
                project_name,
                story_id,
                session_id,
            ),
            width="stretch",
            type="primary",
        ):
            try:
                result = run_with_stream(
                    "正在整理并保存章节...",
                    save_writing_session_as_chapter,
                    project_name,
                    story_id,
                    session_id,
                    int(chapter_no),
                    append_to_existing=append_existing,
                    smooth_transitions=smooth,
                    preview_language=None,
                )
                st.success(
                    f"已将 {result.get('fragment_count', 0)} 个片段保存到第 {chapter_no} 章。"
                )
                st.rerun()
            except FileExistsError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"章节保存失败：{exc}")
