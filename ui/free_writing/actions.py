"""Conversation action receipts and confirmation cards."""

from __future__ import annotations

import json

import streamlit as st

from novelforge.services.memory import list_creative_actions, list_creative_messages
from novelforge.workflows.creative_actions import (
    cancel_creative_action,
    execute_creative_action,
    undo_creative_action,
)
from ui.common import developer_mode_enabled, scoped_widget_key
from ui.streaming import run_with_stream


ACTION_LABELS = {
    "import_sources": "导入资料",
    "extract_knowledge": "提炼设定",
    "query_knowledge": "查询资料",
    "update_knowledge": "修改知识",
    "update_config": "调整配置",
    "save_chapter": "保存章节",
    "clarify": "补充说明",
}


def _humanize_mapping(value: dict) -> str:
    parts = []
    for key, item in value.items():
        label = {
            "category": "分类", "knowledge_id": "知识", "story_id": "故事",
            "chapter_no": "章节", "scope": "范围", "field": "字段",
        }.get(str(key), str(key))
        parts.append(f"{label}：{item}")
    return " · ".join(parts)


def _render_action_card(project_name: str, action: dict) -> None:
    action_id = str(action.get("action_id") or "")
    label = ACTION_LABELS.get(str(action.get("action_type") or ""), "创作动作")
    status = str(action.get("status") or "planned")
    with st.container(border=True):
        st.markdown(f"**{label}** · {status}")
        target = dict(action.get("target") or {})
        patch = dict(action.get("patch") or {})
        if target:
            st.caption("目标：" + (_humanize_mapping(target) if not developer_mode_enabled() else json.dumps(target, ensure_ascii=False)))
        if patch:
            st.caption("拟变更：" + (_humanize_mapping(patch) if not developer_mode_enabled() else json.dumps(patch, ensure_ascii=False)))
        if status == "awaiting_confirmation":
            confirm_col, cancel_col = st.columns(2)
            if confirm_col.button(
                "确认执行", type="primary", width="stretch",
                key=scoped_widget_key("confirm_creative_action", action_id),
            ):
                try:
                    run_with_stream(
                        f"正在执行：{label}...", execute_creative_action,
                        project_name, action_id, confirmed=True,
                        preview_language="json",
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
            if cancel_col.button(
                "取消", width="stretch",
                key=scoped_widget_key("cancel_creative_action", action_id),
            ):
                cancel_creative_action(project_name, action_id)
                st.rerun()
        elif status == "completed" and action.get("undo"):
            if st.button(
                "撤销这次变更", width="stretch",
                key=scoped_widget_key("undo_creative_action", action_id),
            ):
                try:
                    undo_creative_action(project_name, action_id)
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
        elif status == "failed" and action.get("error_text"):
            st.error(str(action.get("error_text")))


def render_creative_action_history(
    project_name: str, story_id: str, session_id: str
) -> None:
    if not session_id:
        return
    actions = [
        item for item in list_creative_actions(project_name, story_id, session_id)
        if item.get("action_type") not in {"write", "revise"}
    ]
    if not actions:
        return
    messages = list_creative_messages(project_name, story_id, session_id)
    message_by_id = {str(item.get("message_id") or ""): item for item in messages}
    receipts: dict[str, list[dict]] = {}
    for message in messages:
        action_id = str(message.get("metadata", {}).get("action_id") or "")
        if action_id:
            receipts.setdefault(action_id, []).append(message)

    with st.expander(f"对话动作（{len(actions)}）", expanded=True):
        for action in actions:
            request = message_by_id.get(str(action.get("request_message_id") or ""), {})
            if request.get("content"):
                with st.chat_message("user"):
                    st.markdown(str(request.get("content")))
            _render_action_card(project_name, action)
            for receipt in receipts.get(str(action.get("action_id") or ""), []):
                with st.chat_message("assistant"):
                    st.markdown(str(receipt.get("content") or ""))
