"""Contextual review panel for knowledge extracted from accepted fragments."""

from __future__ import annotations

import streamlit as st

from novelforge.domain.knowledge_quality import (
    build_pending_issue_map,
    build_pending_knowledge_quality_issues,
)
from novelforge.domain.knowledge_workflows import (
    parse_comma_tags,
    update_pending_knowledge_item,
)
from novelforge.services.memory import (
    KNOWLEDGE_CATEGORIES,
    confirm_pending_knowledge_items,
    discard_pending_knowledge_items,
)
from novelforge.workflows.interactive_writing import (
    active_fragment_chain,
    pending_knowledge_for_fragment,
)
from ui.common import confirmed_button, scoped_widget_key
from ui.labels import label_knowledge_category


def _session_candidates(project_name: str, bundle: dict) -> list[dict]:
    fragment_ids = {
        str(fragment.get("fragment_id") or "")
        for fragment in active_fragment_chain(bundle)
        if str(fragment.get("fragment_id") or "")
    }
    candidates: list[dict] = []
    for fragment_id in fragment_ids:
        candidates.extend(pending_knowledge_for_fragment(project_name, fragment_id))
    deduped = {
        str(item.get("pending_id") or ""): item
        for item in candidates
        if str(item.get("pending_id") or "")
    }
    return list(deduped.values())


def render_knowledge_panel(
    project_name: str,
    story_id: str,
    bundle: dict,
) -> None:
    candidates = _session_candidates(project_name, bundle)
    if not candidates:
        return

    issues = build_pending_knowledge_quality_issues(project_name, candidates)
    issue_map = build_pending_issue_map(issues)
    with st.expander(f"发现 {len(candidates)} 条可保存的新设定", expanded=False):
        st.caption("确认后会进入知识库，并在后续创作中自动匹配使用。")
        labels = {
            str(item.get("pending_id") or ""): _candidate_label(item, issue_map)
            for item in candidates
        }
        for item in candidates:
            _render_candidate_editor(
                project_name,
                story_id,
                item,
                labels,
                issue_map,
            )
        _render_selection_actions(
            project_name,
            story_id,
            bundle,
            labels,
            issue_map,
        )


def _candidate_label(item: dict, issue_map: dict[str, dict]) -> str:
    pending_id = str(item.get("pending_id") or "")
    issue = issue_map.get(pending_id, {})
    suffix = f" · {issue.get('severity')}风险" if issue else ""
    return (
        f"{label_knowledge_category(str(item.get('category') or ''))} · "
        f"{item.get('name') or '未命名'}{suffix}"
    )


def _render_candidate_editor(
    project_name: str,
    story_id: str,
    item: dict,
    labels: dict[str, str],
    issue_map: dict[str, dict],
) -> None:
    pending_id = str(item.get("pending_id") or "")
    issue = issue_map.get(pending_id, {})
    st.markdown(f"**{labels[pending_id]}**")
    st.write(str(item.get("summary") or ""))
    if issue:
        st.warning("；".join(issue.get("descriptions", [])[:2]))

    with st.expander("修改后再保存", expanded=False):
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
            if st.form_submit_button("保存修改", width="stretch"):
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


def _render_selection_actions(
    project_name: str,
    story_id: str,
    bundle: dict,
    labels: dict[str, str],
    issue_map: dict[str, dict],
) -> None:
    safe_default = [
        pending_id
        for pending_id in labels
        if str(issue_map.get(pending_id, {}).get("severity") or "") != "高"
    ]
    session_id = str(bundle.get("session", {}).get("session_id") or "")
    selection_key = scoped_widget_key(
        "creative_pending_selection",
        project_name,
        story_id,
        session_id,
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
        "选择要保存的条目",
        options=list(labels),
        format_func=lambda pending_id: labels[pending_id],
        key=selection_key,
    )
    save_col, discard_col = st.columns(2)
    if save_col.button(
        "保存所选设定",
        disabled=not selected,
        key=scoped_widget_key(
            "creative_confirm_pending",
            project_name,
            story_id,
            session_id,
        ),
        width="stretch",
        type="primary",
    ):
        saved_count = confirm_pending_knowledge_items(project_name, selected)
        st.success(f"已保存 {saved_count} 条设定，后续创作可以立即使用。")
        st.rerun()
    if selected and confirmed_button(
        discard_col,
        "忽略所选",
        "确认忽略所选新设定",
        scoped_widget_key(
            "creative_discard_pending",
            project_name,
            story_id,
            session_id,
        ),
    ):
        removed_count = discard_pending_knowledge_items(project_name, selected)
        st.success(f"已忽略 {removed_count} 条候选设定。")
        st.rerun()
