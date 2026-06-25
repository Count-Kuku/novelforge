"""Resource-browser navigation and selection state helpers."""
from __future__ import annotations

import html

import streamlit as st

from ui.common import _safe_int_metric_value, navigate_to, scoped_widget_key

RESOURCE_BROWSER_GROUPS = [
    ("outline", "全书大纲"),
    ("outline_discussion", "全书讨论工件"),
    ("creative_profile_discussion", "创作配置讨论工件"),
    ("volume_outline", "分卷大纲"),
    ("volume_discussion", "分卷讨论工件"),
    ("arc_outline", "剧情段大纲"),
    ("arc_discussion", "剧情段讨论工件"),
    ("arc_chapter_plan", "剧情段章节分配"),
    ("chapter_outline", "章节细纲"),
    ("chapter_discussion", "章节讨论工件"),
    ("chapter_content", "章节正文"),
    ("review", "审阅结果"),
    ("analysis", "分析报告"),
    ("evaluation", "评估报告"),
    ("run", "流水线记录"),
    ("source", "外部资料"),
    ("knowledge_item", "结构化知识"),
    ("pending_knowledge", "待确认知识"),
    ("long_reference_batch", "资料批次"),
]

RESOURCE_BROWSER_GROUP_LABELS = dict(RESOURCE_BROWSER_GROUPS)

def _normalize_resource_browser_groups(groups: list[str] | tuple[str, ...] | None) -> list[str]:
    allowed_groups = set(RESOURCE_BROWSER_GROUP_LABELS)
    normalized = []
    for group in groups or []:
        group_key = str(group)
        if group_key in allowed_groups and group_key not in normalized:
            normalized.append(group_key)
    return normalized

def _resource_browser_focus_key(project_name: str) -> str:
    return f"resource_browser_focus:{project_name}"

def navigate_to_resource_browser(
    project_name: str,
    groups: list[str] | tuple[str, ...] | None = None,
    *,
    search_value: str = "",
    select_first: bool = True,
):
    st.session_state[_resource_browser_focus_key(project_name)] = {
        "groups": _normalize_resource_browser_groups(groups),
        "search_value": str(search_value or ""),
        "select_first": bool(select_first),
    }
    navigate_to("资源浏览器")

def _consume_resource_browser_focus(project_name: str, browser_items: list[dict]) -> tuple[dict, str]:
    focus = st.session_state.pop(_resource_browser_focus_key(project_name), None)
    if not isinstance(focus, dict):
        return {}, ""

    focus_groups = _normalize_resource_browser_groups(focus.get("groups") or [])
    focus_search = str(focus.get("search_value") or "").strip()

    st.session_state[f"resource_browser_search_{project_name}"] = focus_search
    st.session_state[f"resource_browser_volume_filter_{project_name}"] = 0
    st.session_state[f"resource_browser_arc_filter_{project_name}"] = 0
    if focus_groups:
        st.session_state[f"resource_browser_group_filter_{project_name}"] = focus_groups

    candidates = list(browser_items)
    if focus_groups:
        candidates = [item for item in candidates if item.get("group") in focus_groups]
    if focus_search:
        search_lower = focus_search.lower()
        candidates = [
            item for item in candidates
            if search_lower in str(item.get("label", "")).lower()
            or search_lower in str(item.get("path_label", "")).lower()
        ]

    if candidates and bool(focus.get("select_first", True)):
        selected = candidates[0]
        _set_resource_browser_selection(project_name, selected)
        return selected, ""

    focus_labels = "、".join(RESOURCE_BROWSER_GROUP_LABELS.get(group, group) for group in focus_groups)
    return {}, f"当前没有可定位的{focus_labels or '资源'}。"

def render_resource_metric_link(
    container,
    project_name: str,
    story_id: str,
    label: str,
    value,
    groups: list[str] | tuple[str, ...],
):
    metric_value = _safe_int_metric_value(value)
    normalized_groups = _normalize_resource_browser_groups(groups)
    button_key = scoped_widget_key("overview_resource_metric", project_name, story_id, label, ",".join(normalized_groups))
    with container.container(border=True):
        st.markdown(
            f"""
            <div class="nf-status-label">{html.escape(str(label))}</div>
            <div class="nf-status-value">{metric_value}</div>
            """,
            unsafe_allow_html=True,
        )
        if metric_value > 0 and normalized_groups:
            if st.button("查看资源", key=button_key, use_container_width=True):
                navigate_to_resource_browser(project_name, normalized_groups)
        else:
            disabled_label = "暂无资源" if normalized_groups else "未纳入资源"
            st.button(disabled_label, key=button_key, disabled=True, use_container_width=True)

def _resource_browser_selection_key(project_name: str) -> str:
    return f"resource_browser_selection:{project_name}"

def _set_resource_browser_selection(project_name: str, resource: dict):
    st.session_state[_resource_browser_selection_key(project_name)] = resource

def _get_resource_browser_selection(project_name: str) -> dict:
    return dict(st.session_state.get(_resource_browser_selection_key(project_name), {}))

