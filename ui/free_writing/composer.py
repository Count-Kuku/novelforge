"""Primary free-writing composer and its optional advanced controls."""

from __future__ import annotations

import json

import streamlit as st

from novelforge.domain.setting_knowledge import list_setting_items
from novelforge.domain.creative_actions import route_creative_action
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import label_knowledge_category
from ui.prompt_option_tools import render_context_assembly_summary

from .shared import (
    ACTION_LABELS,
    action_mode_key,
    active_fragment,
    branch_frontier,
    last_result_key,
)
from .preflight import render_writing_preflight
from .attachments import render_attachment_tray
from .execution import run_creative_action, run_creative_generation


def _manual_knowledge_selector(
    project_name: str,
    story_id: str,
    profile: dict,
    session_scope: str,
) -> list[str]:
    manual_items = list_setting_items(
        project_name,
        story_id,
        core_only=False,
        injection_policies={"manual_only"},
        worldline_id=str(profile.get("worldline_id") or ""),
        worldline_mode=str(profile.get("worldline_retrieval_mode") or "prefer"),
    )
    labels = {
        str(item.get("id") or ""): (
            f"{item.get('name') or item.get('summary') or item.get('id')} · "
            f"{label_knowledge_category(str(item.get('category') or ''))}"
        )
        for item in manual_items
        if str(item.get("id") or "")
    }
    return st.multiselect(
        "本次固定参考的知识",
        options=list(labels),
        format_func=lambda item_id: labels.get(item_id, item_id),
        key=scoped_widget_key(
            "creative_manual_knowledge",
            project_name,
            story_id,
            session_scope,
        ),
        help="普通角色卡和世界观会自动匹配；这里只需选择标记为“仅手动使用”的知识。",
    )


def _render_advanced_settings(
    project_name: str,
    story_id: str,
    profile: dict,
    session: dict,
    render_prompt_option_capability_tools,
) -> dict:
    stored_guidance = dict(session.get("writing_guidance") or {})
    session_scope = str(session.get("session_id") or "new")
    with st.expander("高级设置", expanded=False):
        st.caption("不调整也可以直接生成；角色卡、世界观和正式知识会自动匹配。")
        word_count = st.text_input(
            "片段长度",
            value=(
                str(profile.get("target_word_count") or "800-1200")
                if not session
                else "800-1200"
            ),
            key=scoped_widget_key(
                "creative_word_count",
                project_name,
                story_id,
                session_scope,
            ),
        )
        tone_col, pacing_col, dialogue_col = st.columns(3)
        tone_options = ["", "克制", "热血", "轻快", "压抑", "爽文推进"]
        pacing_options = ["", "慢铺", "均衡", "快推"]
        dialogue_options = ["", "低", "中", "高"]
        stored_tone = str(stored_guidance.get("tone") or "")
        stored_pacing = str(stored_guidance.get("pacing") or "")
        stored_dialogue = str(stored_guidance.get("dialogue_density") or "")
        tone = tone_col.selectbox(
            "文风",
            tone_options,
            index=tone_options.index(stored_tone) if stored_tone in tone_options else 0,
            format_func=lambda value: value or "自动",
            key=scoped_widget_key(
                "creative_tone",
                project_name,
                story_id,
                session_scope,
            ),
        )
        pacing = pacing_col.selectbox(
            "节奏",
            pacing_options,
            index=(
                pacing_options.index(stored_pacing)
                if stored_pacing in pacing_options
                else 0
            ),
            format_func=lambda value: value or "自动",
            key=scoped_widget_key(
                "creative_pacing",
                project_name,
                story_id,
                session_scope,
            ),
        )
        dialogue_density = dialogue_col.selectbox(
            "对话密度",
            dialogue_options,
            index=(
                dialogue_options.index(stored_dialogue)
                if stored_dialogue in dialogue_options
                else 0
            ),
            format_func=lambda value: value or "自动",
            key=scoped_widget_key(
                "creative_dialogue",
                project_name,
                story_id,
                session_scope,
            ),
        )
        focus_options = ["动作", "心理", "环境", "关系拉扯", "战斗", "信息揭示"]
        focus = st.multiselect(
            "描写重点",
            focus_options,
            default=[
                value
                for value in stored_guidance.get("focus", [])
                if value in focus_options
            ],
            key=scoped_widget_key(
                "creative_focus",
                project_name,
                story_id,
                session_scope,
            ),
        )
        extra_requirements = st.text_area(
            "持续写作要求",
            value=str(stored_guidance.get("extra_requirements") or ""),
            height=80,
            key=scoped_widget_key(
                "creative_extra",
                project_name,
                story_id,
                session_scope,
            ),
            help="这里的要求会持续作用于整个创作；只影响下一段的要求直接写在主输入框。",
        )
        manual_knowledge_ids = _manual_knowledge_selector(
            project_name,
            story_id,
            profile,
            session_scope,
        )
        prompt_option_ids = render_prompt_option_capability_tools(
            project_name,
            story_id,
            "write",
            scoped_widget_key(
                "creative_prompt_options",
                project_name,
                story_id,
                session_scope,
            ),
            select_for_run=True,
            compact=True,
            show_inline_tools=False,
        )

    writing_guidance = {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "extra_requirements": extra_requirements,
        "manual_knowledge_ids": manual_knowledge_ids,
    }
    if prompt_option_ids is not None:
        writing_guidance["prompt_option_ids"] = prompt_option_ids
    return {
        "word_count": word_count,
        "writing_guidance": writing_guidance,
        "prompt_option_ids": prompt_option_ids,
        "manual_knowledge_ids": manual_knowledge_ids,
    }


def _resolve_action(bundle: dict) -> tuple[str, str | None]:
    fragment = active_fragment(bundle)
    if not fragment:
        return "generate", None

    allowed = {"continue"}
    if str(fragment.get("status") or "") == "proposed":
        allowed.add("rewrite")
    frontier = branch_frontier(bundle)
    if frontier:
        allowed.add("branch")

    session_id = str(bundle.get("session", {}).get("session_id") or "")
    state_key = action_mode_key(session_id)
    action = str(st.session_state.get(state_key) or "continue")
    if action not in allowed:
        action = "continue"
        st.session_state[state_key] = action
    branch_id = (
        str(frontier.get("fragment_id") or "")
        if action == "branch"
        else None
    )
    return action, branch_id


def _render_action_notice(bundle: dict, action: str) -> None:
    if action not in {"rewrite", "branch"}:
        return
    session_id = str(bundle.get("session", {}).get("session_id") or "")
    message_col, cancel_col = st.columns([5, 1], vertical_alignment="center")
    message_col.info(
        "请说明希望如何重写当前片段。"
        if action == "rewrite"
        else "请说明这个新版本接下来要发生什么。"
    )
    if cancel_col.button(
        "取消",
        key=scoped_widget_key("creative_cancel_action", session_id, action),
        width="stretch",
    ):
        st.session_state[action_mode_key(session_id)] = "continue"
        st.rerun()


def render_composer(
    project_name: str,
    story_id: str,
    profile: dict,
    session_id: str,
    bundle: dict,
    session_options: dict,
    render_prompt_option_capability_tools,
) -> None:
    """Render the primary input before any optional configuration."""
    action, branch_id = _resolve_action(bundle) if bundle else ("generate", None)
    session = dict(bundle.get("session", {}) or {})
    archived = bool(bundle) and str(session.get("status") or "") == "archived"
    if archived:
        st.info("这条创作记录已经归档。需要继续时，请先通过上方“管理”恢复。")

    _render_action_notice(bundle, action)
    input_key = scoped_widget_key(
        "creative_user_input",
        project_name,
        story_id,
        session_id or "new",
    )
    clear_flag_key = scoped_session_key(
        "creative_user_input_clear",
        project_name,
        story_id,
        session_id or "new",
    )
    if st.session_state.pop(clear_flag_key, False):
        st.session_state[input_key] = ""

    input_label = {
        "generate": "想先写什么？",
        "continue": "接下来想怎么写？",
        "rewrite": "希望怎样重写这段？",
        "branch": "另一个版本要怎么发展？",
    }[action]
    placeholder = (
        "例如：写一个雨夜相遇的开场，少女似乎认识主角，但暂时不要揭晓。"
        if not bundle
        else "例如：让两人的冲突更明显，并在结尾留下一个新的疑点。"
    )
    user_message = st.text_area(
        input_label,
        height=145,
        key=input_key,
        placeholder=placeholder,
    )
    routed = route_creative_action(
        str(user_message or ""),
        has_fragment=bool(active_fragment(bundle)) if bundle else False,
    )
    routed_type = str(routed.get("action_type") or "write")
    if routed_type == "revise":
        action = "rewrite"
        branch_id = None
    is_tool_action = routed_type not in {"write", "revise"}
    if is_tool_action and str(user_message or "").strip():
        st.info(
            "将作为创作命令处理："
            + {
                "import_sources": "导入资料",
                "extract_knowledge": "提炼设定",
                "query_knowledge": "查询资料",
                "update_knowledge": "修改知识",
                "update_config": "调整配置",
                "save_chapter": "保存章节",
                "clarify": "补充说明",
            }.get(routed_type, routed_type)
        )

    render_attachment_tray(project_name, story_id, session_id)

    config = _render_advanced_settings(
        project_name,
        story_id,
        profile,
        session,
        render_prompt_option_capability_tools,
    )
    if bundle and str(active_fragment(bundle).get("status") or "") == "proposed" and action == "continue":
        st.caption("继续生成成功后，当前片段会自动保留；生成失败不会改变当前内容。")

    estimate_approved = True
    if not is_tool_action:
        estimate_approved = render_writing_preflight(
            project_name,
            story_id,
            session_id,
            bundle,
            str(user_message or "").strip(),
            config["word_count"],
            action_type=action,
            branch_from_fragment_id=branch_id,
            auto_extract_mode=session_options["auto_extract_mode"],
        )

    if st.button(
        "执行创作命令" if is_tool_action else ACTION_LABELS[action],
        disabled=(
            archived
            or not bool(str(user_message or "").strip())
            or not estimate_approved
        ),
        key=scoped_widget_key(
            "creative_generate",
            project_name,
            story_id,
            session_id or "new",
        ),
        width="stretch",
        type="primary",
    ):
        if is_tool_action:
            run_creative_action(
                project_name, story_id, session_id, bundle,
                str(user_message or "").strip(), config, session_options,
            )
        else:
            run_creative_generation(
                project_name,
                story_id,
                session_id,
                bundle,
                action,
                branch_id,
                str(user_message or "").strip(),
                config,
                session_options,
            )
def render_last_context(
    project_name: str,
    story_id: str,
    session_id: str,
) -> None:
    if not session_id:
        return
    result = st.session_state.get(
        last_result_key(project_name, story_id, session_id),
        {},
    )
    if not result:
        return
    for warning in result.get("warnings", []):
        st.warning(warning)
    render_context_assembly_summary(
        result.get("context_assembly", {}),
        "上一轮使用了哪些资料",
    )
    with st.expander("技术信息（排查问题时使用）", expanded=False):
        st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")
