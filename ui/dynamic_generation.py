"""Low-friction single-turn and iterative creative-writing workspace."""
from __future__ import annotations

import json

import streamlit as st

from novelforge.workflows.interactive_writing import (
    accept_writing_fragment,
    active_fragment_chain,
    compile_session_text,
    create_writing_session,
    extract_fragment_knowledge,
    generate_writing_fragment,
    pending_knowledge_for_fragment,
    preview_writing_context,
    save_writing_session_as_chapter,
    select_writing_fragment_variant,
)
from novelforge.domain.knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
)
from novelforge.domain.knowledge_workflows import parse_comma_tags, update_pending_knowledge_item
from novelforge.services.memory import (
    KNOWLEDGE_CATEGORIES,
    confirm_pending_knowledge_items,
    discard_pending_knowledge_items,
    list_creative_sessions,
    load_creative_profile,
    load_creative_session_bundle,
    update_creative_session,
)
from novelforge.domain.setting_knowledge import list_setting_items
from ui.common import confirmed_button, scoped_session_key, scoped_widget_key
from ui.context_directives import render_context_directive_tools
from ui.labels import label_knowledge_category
from ui.layout import render_section_heading
from ui.prompt_option_tools import render_context_assembly_summary
from ui.streaming import run_with_stream


ACTION_LABELS = {
    "generate": "生成第一个片段",
    "continue": "承接当前片段继续写",
    "rewrite": "重写当前候选片段",
    "branch": "从已接受片段创建分支",
}
FRAGMENT_STATUS_LABELS = {
    "proposed": "待接受",
    "accepted": "已接受",
    "superseded": "已被重写",
    "discarded": "已放弃",
    "finalized": "已并入章节",
}
SESSION_STATUS_LABELS = {
    "active": "创作中",
    "completed": "已完成",
    "archived": "已归档",
}


def _active_session_key(project_name: str, story_id: str) -> str:
    return scoped_session_key("creative_active_session", project_name, story_id)


def _last_result_key(project_name: str, story_id: str, session_id: str) -> str:
    return scoped_session_key(
        "creative_last_result",
        project_name,
        story_id,
        session_id,
    )


def _select_session(project_name: str, story_id: str) -> str:
    sessions = list_creative_sessions(project_name, story_id, include_archived=True)
    session_map = {
        str(item.get("session_id") or ""): item
        for item in sessions
        if str(item.get("session_id") or "")
    }
    state_key = _active_session_key(project_name, story_id)
    current = str(st.session_state.get(state_key) or "")
    if current and current not in session_map:
        current = ""
        st.session_state[state_key] = ""
    elif state_key not in st.session_state:
        st.session_state[state_key] = current
    options = [""] + list(session_map)
    selected = st.selectbox(
        "继续已有创作",
        options=options,
        format_func=lambda value: (
            "开始新的创作"
            if not value
            else (
                f"{session_map[value].get('title') or value} · "
                f"{SESSION_STATUS_LABELS.get(str(session_map[value].get('status') or ''), '未知状态')}"
            )
        ),
        key=state_key,
    )
    return selected


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
        help="这里只显示设置为“仅在手动选择时使用”的知识；普通角色卡和世界观资料会根据本轮内容自动匹配。",
    )


def _render_writing_config(
    project_name: str,
    story_id: str,
    profile: dict,
    session: dict,
    render_prompt_option_capability_tools,
) -> dict:
    stored_guidance = dict(session.get("writing_guidance") or {})
    session_scope = str(session.get("session_id") or "new")
    with st.expander("可选设置：片段长度、文风与参考资料", expanded=False):
        word_count = st.text_input(
            "本轮片段字数",
            value=str(profile.get("target_word_count") or "800-1200")
            if not session
            else "800-1200",
            key=scoped_widget_key("creative_word_count", project_name, story_id, session_scope),
        )
        col_a, col_b, col_c = st.columns(3)
        tone_options = ["", "克制", "热血", "轻快", "压抑", "爽文推进"]
        pacing_options = ["", "慢铺", "均衡", "快推"]
        dialogue_options = ["", "低", "中", "高"]
        tone = col_a.selectbox(
            "文风/基调",
            tone_options,
            index=tone_options.index(stored_guidance.get("tone", ""))
            if stored_guidance.get("tone", "") in tone_options else 0,
            format_func=lambda value: value or "未指定",
            key=scoped_widget_key("creative_tone", project_name, story_id, session_scope),
        )
        pacing = col_b.selectbox(
            "节奏",
            pacing_options,
            index=pacing_options.index(stored_guidance.get("pacing", ""))
            if stored_guidance.get("pacing", "") in pacing_options else 0,
            format_func=lambda value: value or "未指定",
            key=scoped_widget_key("creative_pacing", project_name, story_id, session_scope),
        )
        dialogue_density = col_c.selectbox(
            "对话密度",
            dialogue_options,
            index=dialogue_options.index(stored_guidance.get("dialogue_density", ""))
            if stored_guidance.get("dialogue_density", "") in dialogue_options else 0,
            format_func=lambda value: value or "未指定",
            key=scoped_widget_key("creative_dialogue", project_name, story_id, session_scope),
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
            key=scoped_widget_key("creative_focus", project_name, story_id, session_scope),
        )
        extra_requirements = st.text_area(
            "整个会话持续生效的要求",
            value=str(stored_guidance.get("extra_requirements") or ""),
            height=80,
            key=scoped_widget_key("creative_extra", project_name, story_id, session_scope),
            help="会话内持续生效；临时要求直接写在下一轮输入中。",
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
            scoped_widget_key("creative_prompt_options", project_name, story_id, session_scope),
            select_for_run=True,
        )
    guidance = {
        "tone": tone,
        "pacing": pacing,
        "dialogue_density": dialogue_density,
        "focus": focus,
        "extra_requirements": extra_requirements,
        "manual_knowledge_ids": manual_knowledge_ids,
    }
    if prompt_option_ids is not None:
        guidance["prompt_option_ids"] = prompt_option_ids
    return {
        "word_count": word_count,
        "writing_guidance": guidance,
        "prompt_option_ids": prompt_option_ids,
        "manual_knowledge_ids": manual_knowledge_ids,
    }


def _render_session_settings(
    project_name: str,
    story_id: str,
    session: dict,
) -> dict:
    if not session:
        target_col, setting_col = st.columns(2)
        target_chapter_no = target_col.number_input(
            "准备整理到第几章（0 表示稍后决定）",
            min_value=0,
            value=0,
            key=scoped_widget_key("creative_new_target_chapter", project_name, story_id),
        )
        setting_col.caption("新设定处理")
        auto_extract = setting_col.checkbox(
            "接受片段后，自动找出可保存的新设定",
            value=True,
            key=scoped_widget_key("creative_new_auto_extract", project_name, story_id),
            help="系统只会生成待审核设定；由你确认后才会写入正式知识库。",
        )
        return {
            "target_chapter_no": int(target_chapter_no) or None,
            "auto_extract_mode": "on_accept" if auto_extract else "manual",
        }

    with st.expander("会话设置", expanded=False):
        title = st.text_input(
            "会话标题",
            value=str(session.get("title") or ""),
            key=scoped_widget_key("creative_session_title", project_name, story_id, session.get("session_id")),
        )
        goal = st.text_area(
            "会话目标",
            value=str(session.get("session_goal") or ""),
            height=90,
            key=scoped_widget_key("creative_session_goal", project_name, story_id, session.get("session_id")),
        )
        target_chapter_no = st.number_input(
            "准备整理到第几章（0 表示稍后决定）",
            min_value=0,
            value=int(session.get("target_chapter_no") or 0),
            key=scoped_widget_key("creative_target_chapter", project_name, story_id, session.get("session_id")),
        )
        auto_extract = st.checkbox(
            "接受片段后，自动找出可保存的新设定",
            value=session.get("auto_extract_mode") == "on_accept",
            key=scoped_widget_key("creative_auto_extract", project_name, story_id, session.get("session_id")),
        )
        save_col, archive_col = st.columns(2)
        if save_col.button(
            "保存会话设置",
            key=scoped_widget_key("creative_save_session", project_name, story_id, session.get("session_id")),
            use_container_width=True,
        ):
            update_creative_session(
                project_name,
                str(session["session_id"]),
                {
                    "title": title,
                    "session_goal": goal,
                    "target_chapter_no": int(target_chapter_no) or None,
                    "auto_extract_mode": "on_accept" if auto_extract else "manual",
                },
                story_id=story_id,
            )
            st.success("会话设置已保存。")
            st.rerun()
        archived = str(session.get("status") or "") == "archived"
        if archive_col.button(
            "恢复会话" if archived else "归档会话",
            key=scoped_widget_key("creative_archive_session", project_name, story_id, session.get("session_id")),
            use_container_width=True,
        ):
            update_creative_session(
                project_name,
                str(session["session_id"]),
                {"status": "active" if archived else "archived"},
                story_id=story_id,
            )
            st.rerun()
    return {
        "target_chapter_no": int(target_chapter_no) or None,
        "auto_extract_mode": "on_accept" if auto_extract else "manual",
    }


def _render_fragment_chat(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    turns = {
        str(turn.get("turn_id") or ""): turn
        for turn in bundle.get("turns", [])
        if str(turn.get("turn_id") or "")
    }
    chain = active_fragment_chain(bundle)
    if not chain:
        st.caption("当前会话还没有生成片段。")
        return
    for fragment in chain:
        turn = turns.get(str(fragment.get("turn_id") or ""), {})
        with st.chat_message("user"):
            st.markdown(str(turn.get("user_message") or "继续创作"))
        with st.chat_message("assistant"):
            st.markdown(str(fragment.get("content") or ""))
            status = FRAGMENT_STATUS_LABELS.get(
                str(fragment.get("status") or ""),
                str(fragment.get("status") or ""),
            )
            st.caption(
                f"{status} · {fragment.get('word_count') or len(str(fragment.get('content') or ''))} 字符"
            )

    active_ids = {str(item.get("fragment_id") or "") for item in chain}
    alternatives = [
        fragment
        for fragment in bundle.get("fragments", [])
        if str(fragment.get("fragment_id") or "") not in active_ids
    ]
    if alternatives:
        with st.expander(f"其它版本（{len(alternatives)}）", expanded=False):
            for fragment in alternatives:
                st.caption(
                    f"{FRAGMENT_STATUS_LABELS.get(str(fragment.get('status') or ''), fragment.get('status'))} · "
                    f"{str(fragment.get('fragment_id') or '')[:20]}"
                )
                st.markdown(str(fragment.get("content") or ""))
                active = _active_fragment(bundle)
                archived = (
                    str(bundle.get("session", {}).get("status") or "")
                    == "archived"
                )
                can_select = (
                    not archived
                    and
                    str(fragment.get("status") or "") == "proposed"
                    and str(active.get("status") or "") == "proposed"
                    and str(fragment.get("parent_fragment_id") or "")
                    == str(active.get("parent_fragment_id") or "")
                )
                if st.button(
                    "设为当前候选",
                    disabled=not can_select,
                    key=scoped_widget_key(
                        "creative_select_variant",
                        project_name,
                        story_id,
                        fragment.get("fragment_id"),
                    ),
                ):
                    select_writing_fragment_variant(
                        project_name,
                        story_id,
                        str(bundle.get("session", {}).get("session_id") or ""),
                        str(fragment.get("fragment_id") or ""),
                    )
                    st.rerun()


def _active_fragment(bundle: dict) -> dict:
    session = bundle.get("session", {}) or {}
    active_id = str(session.get("active_fragment_id") or "")
    for fragment in bundle.get("fragments", []):
        if str(fragment.get("fragment_id") or "") == active_id:
            return fragment
    return {}


def _render_active_fragment_actions(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    fragment = _active_fragment(bundle)
    if not fragment:
        return
    session_id = str(bundle.get("session", {}).get("session_id") or "")
    fragment_id = str(fragment.get("fragment_id") or "")
    status = str(fragment.get("status") or "")
    archived = str(bundle.get("session", {}).get("status") or "") == "archived"
    accept_col, extract_col = st.columns(2)
    if accept_col.button(
        "接受当前片段",
        disabled=archived or status != "proposed",
        key=scoped_widget_key("creative_accept_fragment", project_name, story_id, fragment_id),
        use_container_width=True,
        type="primary" if status == "proposed" else "secondary",
    ):
        result = accept_writing_fragment(
            project_name,
            story_id,
            session_id,
            fragment_id,
        )
        for warning in result.get("warnings", []):
            st.warning(warning)
        st.rerun()
    if extract_col.button(
        "提炼候选设定",
        disabled=archived or status not in {"accepted", "finalized"},
        key=scoped_widget_key("creative_extract_fragment", project_name, story_id, fragment_id),
        use_container_width=True,
    ):
        try:
            result = run_with_stream(
                "正在提炼片段知识...",
                extract_fragment_knowledge,
                project_name,
                story_id,
                session_id,
                fragment_id,
                preview_language="json",
            )
            st.success(f"已整理 {len(result.get('candidate_ids', []))} 条候选设定。")
            st.rerun()
        except Exception as exc:
            st.error(f"片段设定提炼失败：{exc}")


def _render_fragment_knowledge(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    fragment_ids = {
        str(fragment.get("fragment_id") or "")
        for fragment in active_fragment_chain(bundle)
        if str(fragment.get("fragment_id") or "")
    }
    candidates = []
    for fragment_id in fragment_ids:
        candidates.extend(pending_knowledge_for_fragment(project_name, fragment_id))
    deduped = {
        str(item.get("pending_id") or ""): item
        for item in candidates
        if str(item.get("pending_id") or "")
    }
    candidates = list(deduped.values())
    if not candidates:
        return
    issues = build_pending_knowledge_quality_issues(project_name, candidates)
    issue_map = build_pending_issue_map(issues)
    with st.expander(f"本会话待审核设定（{len(candidates)}）", expanded=True):
        st.caption("确认后立即进入正式知识库并参与后续检索；高风险重复或冲突建议到“资料导入”详细处理。")
        labels = {}
        for item in candidates:
            pending_id = str(item.get("pending_id") or "")
            issue = issue_map.get(pending_id, {})
            suffix = f" · {issue.get('severity')}风险" if issue else ""
            labels[pending_id] = (
                f"{label_knowledge_category(str(item.get('category') or ''))} · "
                f"{item.get('name') or '未命名'}{suffix}"
            )
            st.markdown(f"**{labels[pending_id]}**")
            st.write(str(item.get("summary") or ""))
            if issue:
                st.warning("；".join(issue.get("descriptions", [])[:2]))
            with st.expander("就地修正后再确认", expanded=False):
                category_options = list(KNOWLEDGE_CATEGORIES)
                current_category = str(item.get("category") or "")
                if current_category not in category_options:
                    current_category = category_options[0]
                with st.form(
                    scoped_widget_key(
                        "creative_pending_edit_form",
                        project_name,
                        story_id,
                        pending_id,
                    )
                ):
                    category = st.selectbox(
                        "分类",
                        category_options,
                        index=category_options.index(current_category),
                        format_func=label_knowledge_category,
                        key=scoped_widget_key(
                            "creative_pending_category",
                            project_name,
                            story_id,
                            pending_id,
                        ),
                    )
                    name = st.text_input(
                        "名称",
                        value=str(item.get("name") or ""),
                        key=scoped_widget_key(
                            "creative_pending_name",
                            project_name,
                            story_id,
                            pending_id,
                        ),
                    )
                    summary = st.text_area(
                        "设定内容",
                        value=str(item.get("summary") or ""),
                        height=110,
                        key=scoped_widget_key(
                            "creative_pending_summary",
                            project_name,
                            story_id,
                            pending_id,
                        ),
                    )
                    tags = st.text_input(
                        "标签（逗号分隔）",
                        value="，".join(
                            str(tag)
                            for tag in item.get("tags", [])
                            if str(tag).strip()
                        ),
                        key=scoped_widget_key(
                            "creative_pending_tags",
                            project_name,
                            story_id,
                            pending_id,
                        ),
                    )
                    if st.form_submit_button("保存修正", use_container_width=True):
                        if not summary.strip():
                            st.warning("设定内容不能为空。")
                        else:
                            update_pending_knowledge_item(
                                project_name,
                                pending_id,
                                {
                                    "category": category,
                                    "name": name.strip() or summary.strip()[:36],
                                    "summary": summary.strip(),
                                    "tags": parse_comma_tags(tags),
                                },
                            )
                            st.success("候选设定已更新。")
                            st.rerun()
        safe_default = [
            pending_id for pending_id in labels
            if str(issue_map.get(pending_id, {}).get("severity") or "") not in {"高"}
        ]
        selection_key = scoped_widget_key(
            "creative_pending_selection",
            project_name,
            story_id,
            bundle.get("session", {}).get("session_id"),
        )
        if selection_key not in st.session_state:
            st.session_state[selection_key] = safe_default
        else:
            stored_selection = [
                str(pending_id)
                for pending_id in st.session_state.get(selection_key, [])
            ]
            valid_selection = [
                pending_id
                for pending_id in stored_selection
                if pending_id in labels
            ]
            st.session_state[selection_key] = (
                safe_default
                if stored_selection and not valid_selection
                else valid_selection
            )
        selected = st.multiselect(
            "选择要确认的条目",
            options=list(labels),
            format_func=lambda pending_id: labels[pending_id],
            key=selection_key,
        )
        confirm_col, discard_col = st.columns(2)
        if confirm_col.button(
            "确认所选条目",
            disabled=not selected,
            key=scoped_widget_key("creative_confirm_pending", project_name, story_id, bundle.get("session", {}).get("session_id")),
            use_container_width=True,
        ):
            saved_count = confirm_pending_knowledge_items(project_name, selected)
            st.success(f"已确认 {saved_count} 条知识，后续生成可立即检索使用。")
            st.rerun()
        if selected and confirmed_button(
            discard_col,
            "丢弃所选",
            "确认丢弃所选候选设定",
            scoped_widget_key("creative_discard_pending", project_name, story_id, bundle.get("session", {}).get("session_id")),
        ):
            removed_count = discard_pending_knowledge_items(project_name, selected)
            st.success(f"已丢弃 {removed_count} 条候选设定。")
            st.rerun()


def _action_for_bundle(bundle: dict) -> tuple[str, str | None]:
    fragment = _active_fragment(bundle)
    if not fragment:
        return "generate", None
    options = ["continue"]
    if str(fragment.get("status") or "") == "proposed":
        options.append("rewrite")
    chain = active_fragment_chain(bundle)
    branch_frontier = {}
    if str(fragment.get("status") or "") in {"accepted", "finalized"}:
        branch_frontier = fragment
    elif str(fragment.get("status") or "") == "proposed":
        parent_id = str(fragment.get("parent_fragment_id") or "")
        branch_frontier = next(
            (
                item
                for item in chain
                if str(item.get("fragment_id") or "") == parent_id
                and str(item.get("status") or "") in {"accepted", "finalized"}
            ),
            {},
        )
    if branch_frontier:
        options.append("branch")
    action_key = scoped_widget_key(
        "creative_action",
        bundle.get("session", {}).get("session_id"),
    )
    if st.session_state.get(action_key) not in options:
        st.session_state[action_key] = options[0]
    action = st.radio(
        "本轮操作",
        options=options,
        horizontal=True,
        format_func=lambda value: ACTION_LABELS[value],
        key=action_key,
    )
    branch_id = None
    if action == "branch":
        branch_options = [str(branch_frontier.get("fragment_id") or "")]
        branch_key = scoped_widget_key(
            "creative_branch_from",
            bundle.get("session", {}).get("session_id"),
        )
        if st.session_state.get(branch_key) not in branch_options:
            st.session_state[branch_key] = branch_options[0]
        branch_id = st.selectbox(
            "分支起点",
            options=branch_options,
            format_func=lambda fragment_id: (
                f"当前创作前沿 · {str(branch_frontier.get('content') or '')[:50]}"
            ),
            key=branch_key,
            help="会话内分支只比较当前进展中的候选，避免旧分支设定混入当前资料；如果想保留更早章节开始的另一条剧情线，请复制为新故事。",
        )
    return action, branch_id


def _render_context_preview(
    project_name: str,
    story_id: str,
    session_id: str,
    user_message: str,
    action: str,
    config: dict,
    branch_id: str | None,
) -> None:
    with st.expander("预览：本轮会使用哪些规则与资料", expanded=False):
        preview_key = scoped_session_key(
            "creative_context_preview",
            project_name,
            story_id,
            session_id,
        )
        if st.button(
            "刷新预览",
            disabled=not bool(str(user_message or "").strip()),
            key=scoped_widget_key("creative_preview_refresh", project_name, story_id, session_id),
        ):
            try:
                assembly = preview_writing_context(
                    project_name,
                    story_id,
                    session_id,
                    user_message,
                    action_type=action,
                    writing_guidance=config["writing_guidance"],
                    prompt_option_ids=config["prompt_option_ids"],
                    manual_knowledge_ids=config["manual_knowledge_ids"],
                    branch_from_fragment_id=branch_id,
                )
                st.session_state[preview_key] = assembly.model_dump()
            except Exception as exc:
                st.error(f"本轮使用内容预览失败：{exc}")
        preview = st.session_state.get(preview_key, {})
        if preview:
            render_context_assembly_summary(preview, "本轮预计使用的内容")


def _render_generation_form(
    project_name: str,
    story_id: str,
    session_id: str,
    bundle: dict,
    config: dict,
    session_options: dict,
) -> None:
    action, branch_id = _action_for_bundle(bundle) if bundle else ("generate", None)
    archived = (
        bool(bundle)
        and str(bundle.get("session", {}).get("status") or "") == "archived"
    )
    if archived:
        st.info("该会话已归档。需要继续创作时，请先在“会话设置”中恢复。")
    if bundle and str(_active_fragment(bundle).get("status") or "") == "proposed":
        st.caption("继续写会在新片段成功保存时自动接受当前候选；若生成失败，候选状态不会改变。")
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
    user_message = st.text_area(
        "你希望模型怎么写",
        height=150,
        key=input_key,
        placeholder=(
            "例如：写一个雨夜相遇的开场。生成一次后可以直接离开，也可以继续输入要求逐段创作。"
            if not bundle
            else "例如：继续写，让少女表现出她其实认识主角，但不要立刻揭晓。"
        ),
    )
    if bundle and not archived:
        _render_context_preview(
            project_name,
            story_id,
            session_id,
            user_message,
            action,
            config,
            branch_id,
        )
    if st.button(
        ACTION_LABELS[action],
        disabled=archived or not bool(str(user_message or "").strip()),
        key=scoped_widget_key("creative_generate", project_name, story_id, session_id or "new"),
        use_container_width=True,
        type="primary",
    ):
        try:
            effective_session_id = session_id
            if not bundle:
                created = create_writing_session(
                    project_name,
                    story_id,
                    session_goal=user_message,
                    writing_guidance=config["writing_guidance"],
                    target_chapter_no=session_options["target_chapter_no"],
                    auto_extract_mode=session_options["auto_extract_mode"],
                )
                effective_session_id = str(created["session_id"])
                st.session_state[_active_session_key(project_name, story_id)] = effective_session_id
            else:
                update_creative_session(
                    project_name,
                    effective_session_id,
                    {
                        "writing_guidance": config["writing_guidance"],
                        "target_chapter_no": session_options["target_chapter_no"],
                        "auto_extract_mode": session_options["auto_extract_mode"],
                    },
                    story_id=story_id,
                )
            result = run_with_stream(
                "正在生成创作片段...",
                generate_writing_fragment,
                project_name,
                story_id,
                effective_session_id,
                user_message,
                action_type=action,
                word_count=config["word_count"],
                writing_guidance=config["writing_guidance"],
                prompt_option_ids=config["prompt_option_ids"],
                manual_knowledge_ids=config["manual_knowledge_ids"],
                branch_from_fragment_id=branch_id,
            )
            st.session_state[
                _last_result_key(project_name, story_id, effective_session_id)
            ] = result
            st.session_state[scoped_session_key(
                "creative_user_input_clear",
                project_name,
                story_id,
                effective_session_id,
            )] = True
            st.rerun()
        except Exception as exc:
            st.error(f"生成失败：{exc}")


def _render_actual_context(
    project_name: str,
    story_id: str,
    session_id: str,
) -> None:
    if not session_id:
        return
    result = st.session_state.get(
        _last_result_key(project_name, story_id, session_id),
        {},
    )
    if not result:
        return
    for warning in result.get("warnings", []):
        st.warning(warning)
    render_context_assembly_summary(
        result.get("context_assembly", {}),
        "上一轮实际使用的上下文",
    )
    with st.expander("上一轮详细数据", expanded=False):
        st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


def _render_chapter_compile(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    compiled = compile_session_text(bundle)
    if not compiled.strip():
        return
    session = bundle.get("session", {}) or {}
    archived = str(session.get("status") or "") == "archived"
    with st.expander("整理为正式章节", expanded=False):
        st.caption("只会合并当前分支的已接受片段；未接受和被重写版本不会进入章节。")
        st.text_area(
            "章节预览",
            value=compiled,
            height=320,
            disabled=True,
            key=scoped_widget_key("creative_compile_preview", project_name, story_id, session.get("session_id")),
        )
        chapter_no = st.number_input(
            "保存到章节",
            min_value=1,
            value=int(session.get("target_chapter_no") or 1),
            key=scoped_widget_key("creative_compile_chapter", project_name, story_id, session.get("session_id")),
        )
        append_existing = st.checkbox(
            "若章节已有正文，则追加到末尾",
            value=False,
            key=scoped_widget_key("creative_compile_append", project_name, story_id, session.get("session_id")),
        )
        smooth = st.checkbox(
            "使用模型润色片段衔接",
            value=False,
            key=scoped_widget_key("creative_compile_smooth", project_name, story_id, session.get("session_id")),
        )
        if st.button(
            "保存为正式章节",
            disabled=archived,
            key=scoped_widget_key("creative_compile_save", project_name, story_id, session.get("session_id")),
            use_container_width=True,
            type="primary",
        ):
            try:
                result = run_with_stream(
                    "正在整理并保存章节...",
                    save_writing_session_as_chapter,
                    project_name,
                    story_id,
                    str(session["session_id"]),
                    int(chapter_no),
                    append_to_existing=append_existing,
                    smooth_transitions=smooth,
                    preview_language=None,
                )
                st.success(
                    f"已将 {result.get('fragment_count', 0)} 个片段保存为第 {chapter_no} 章。"
                )
                st.rerun()
            except FileExistsError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"章节保存失败：{exc}")


def render_dynamic_generation_page(project_name: str, render_prompt_option_capability_tools):
    story_id = st.session_state.get("active_story_id", "default")
    profile = load_creative_profile(project_name, story_id=story_id) or {}
    render_section_heading(
        "自由创作",
        "直接描述想写的内容即可生成片段；继续发送要求就能续写。满意的片段可以整理为章节，新设定也能保存到知识库。",
    )
    session_id = _select_session(project_name, story_id)
    bundle = (
        load_creative_session_bundle(project_name, session_id, story_id=story_id)
        if session_id
        else None
    )
    session = dict((bundle or {}).get("session") or {})
    session_options = _render_session_settings(
        project_name,
        story_id,
        session,
    )
    config = _render_writing_config(
        project_name,
        story_id,
        profile,
        session,
        render_prompt_option_capability_tools,
    )
    effective_chapter_no = int(session_options.get("target_chapter_no") or 1)
    render_context_directive_tools(
        project_name,
        story_id,
        capability="write",
        chapter_no=effective_chapter_no,
    )

    if bundle:
        render_section_heading(
            "当前片段链",
            "续写沿当前分支前进；重写会保留旧版本，但不会把旧版本带入当前上下文。",
        )
        _render_fragment_chat(project_name, story_id, bundle)
        _render_active_fragment_actions(project_name, story_id, bundle)
        _render_fragment_knowledge(project_name, story_id, bundle)
        _render_chapter_compile(project_name, story_id, bundle)

    render_section_heading(
        "输入本轮要求",
        "系统会自动匹配相关的角色卡、世界观和正式知识；只有设置为“仅在手动选择时使用”的内容需要到可选设置中指定。",
    )
    _render_generation_form(
        project_name,
        story_id,
        session_id,
        bundle or {},
        config,
        session_options,
    )
    _render_actual_context(project_name, story_id, session_id)
