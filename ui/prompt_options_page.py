"""提示词选项页面。"""
from __future__ import annotations

import streamlit as st

from memory import (
    list_stories,
    load_global_prompt_options,
    load_project_prompt_options,
    load_story_prompt_options,
    upsert_prompt_option,
)
from prompt_options import (
    PROMPT_OPTION_CAPABILITIES,
    PROMPT_OPTION_CATEGORIES,
    builtin_prompt_options,
    filter_prompt_options,
    format_prompt_options_for_prompt,
    merge_prompt_option_layers,
)
from ui.common import scoped_widget_key
from ui.prompt_option_tools import (
    PROMPT_OPTION_LAYER_LABELS,
    _prompt_option_label,
    _render_prompt_option_create_form,
    _render_prompt_option_layer,
)


def _load_prompt_option_page_context(project_name: str, story_id: str) -> dict:
    stories = list_stories(project_name)
    current_story_name = next((s.get("name", story_id) for s in stories if s.get("story_id") == story_id), story_id)
    global_options = load_global_prompt_options()
    project_options = load_project_prompt_options(project_name)
    story_options = load_story_prompt_options(project_name, story_id)
    effective_options = merge_prompt_option_layers(global_options, project_options, story_options)
    return {
        "current_story_name": current_story_name,
        "global_options": global_options,
        "project_options": project_options,
        "story_options": story_options,
        "effective_options": effective_options,
    }


def _prompt_option_records(context: dict) -> list[tuple[str, dict]]:
    return (
        [("story", option) for option in context["story_options"]]
        + [("project", option) for option in context["project_options"]]
        + [("global", option) for option in context["global_options"]]
        + [("builtin", option) for option in builtin_prompt_options()]
    )


def _prompt_option_overview_rows(all_records: list[tuple[str, dict]], query: str, capability_filter: str) -> list[dict]:
    rows = []
    for layer, option in all_records:
        haystack = " ".join([
            str(option.get("id", "")),
            str(option.get("name", "")),
            str(option.get("content", "")),
            " ".join(option.get("tags", []) or []),
        ]).lower()
        option_capability = str(option.get("capability") or "")
        if query and query not in haystack:
            continue
        if capability_filter and option_capability not in {capability_filter, "all"}:
            continue
        rows.append({
            "层级": PROMPT_OPTION_LAYER_LABELS.get(layer, layer),
            "名称": option.get("name") or option.get("id"),
            "适用能力": PROMPT_OPTION_CAPABILITIES.get(option_capability, option_capability),
            "类型": PROMPT_OPTION_CATEGORIES.get(option.get("category", ""), option.get("category", "")),
            "状态": "启用" if option.get("enabled", True) else "停用",
            "优先级": option.get("priority", 50),
            "ID": option.get("id", ""),
        })
    return rows


def _render_prompt_options_overview(all_records: list[tuple[str, dict]]) -> None:
    query = st.text_input("搜索提示词", placeholder="输入名称、ID、内容或标签", key="prompt_option_overview_query").strip().lower()
    capability_filter = st.selectbox(
        "按适用能力筛选",
        options=[""] + list(PROMPT_OPTION_CAPABILITIES.keys()),
        format_func=lambda value: "全部能力" if not value else PROMPT_OPTION_CAPABILITIES.get(value, value),
        key="prompt_option_overview_capability",
    )
    rows = _prompt_option_overview_rows(all_records, query, capability_filter)
    st.caption(f"共找到 {len(rows)} 个提示词选项。")
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("没有匹配的提示词选项。")


def _render_prompt_options_create_tabs(project_name: str, story_id: str, current_story_name: str) -> None:
    tab_story_new, tab_project_new, tab_global_new = st.tabs([
        f"新增到当前故事：{current_story_name}",
        "新增到项目",
        "新增到全局",
    ])
    with tab_story_new:
        _render_prompt_option_create_form(project_name, story_id, "story", "new_prompt_option_form_story")
    with tab_project_new:
        _render_prompt_option_create_form(project_name, story_id, "project", "new_prompt_option_form_project")
    with tab_global_new:
        _render_prompt_option_create_form(project_name, story_id, "global", "new_prompt_option_form_global")


def _render_prompt_options_manage_tabs(project_name: str, story_id: str, current_story_name: str) -> None:
    tab_story, tab_project, tab_global = st.tabs([
        f"当前故事：{current_story_name}",
        "项目",
        "全局",
    ])
    with tab_story:
        _render_prompt_option_layer(project_name, story_id, "story")
    with tab_project:
        _render_prompt_option_layer(project_name, story_id, "project")
    with tab_global:
        _render_prompt_option_layer(project_name, story_id, "global")


def _render_builtin_prompt_options(project_name: str, story_id: str) -> None:
    st.caption("内置预设默认不直接生效；复制到当前故事后可以编辑并启用。")
    for option in builtin_prompt_options():
        with st.expander(_prompt_option_label(option), expanded=False):
            st.write(option.get("content", ""))
            if st.button("复制到当前故事并启用", key=scoped_widget_key("copy_builtin_prompt_option", project_name, story_id, option.get("id", ""))):
                payload = dict(option)
                payload["scope"] = "story"
                payload["built_in"] = False
                payload["enabled"] = True
                payload["source"] = "builtin_copy"
                upsert_prompt_option(project_name, "story", payload, story_id=story_id)
                st.success("已复制到当前故事并启用。")
                st.rerun()


def _render_prompt_options_preview(effective_options: list[dict]) -> None:
    capability_keys = list(PROMPT_OPTION_CAPABILITIES.keys())
    capability = st.selectbox(
        "预览能力",
        options=capability_keys,
        format_func=lambda value: PROMPT_OPTION_CAPABILITIES.get(value, value),
        index=capability_keys.index("write"),
        key="prompt_option_preview_capability",
    )
    active_options = filter_prompt_options(effective_options, capability)
    st.caption(f"当前生效选项：{len(active_options)} 个")
    preview = format_prompt_options_for_prompt(effective_options, capability)
    if preview:
        st.code(preview, language="markdown")
    else:
        st.info("当前能力没有启用的提示词选项。")


def render_prompt_options_page(project_name: str):
    story_id = st.session_state.get("active_story_id", "default")
    context = _load_prompt_option_page_context(project_name, story_id)

    st.subheader("提示词选项工作台")
    st.caption("把这里当成“本次生成可以选择启用的写作方式”。它们适合描述文风、节奏、描写重点、规划方法和审稿关注点；如果内容属于不能违反的设定事实、边界或禁忌，请放到生成规则。")
    st.info("提示词选项不需要先讨论才会出现。你可以在「新增」里手动创建，也可以在「内置预设」里复制现成选项；讨论只是另一种把建议保存成选项的方式。")
    st.caption("它决定的是生成时额外注入哪些可切换提示，例如“正文更快节奏”“多写心理活动”“审稿时重点检查人物 OOC”。")

    tab_overview, tab_create, tab_manage, tab_builtin, tab_preview = st.tabs([
        "全部总览",
        "新增",
        "增删改",
        "内置预设",
        "生效预览",
    ])
    all_records = _prompt_option_records(context)
    with tab_overview:
        _render_prompt_options_overview(all_records)
    with tab_create:
        _render_prompt_options_create_tabs(project_name, story_id, context["current_story_name"])
    with tab_manage:
        _render_prompt_options_manage_tabs(project_name, story_id, context["current_story_name"])
    with tab_builtin:
        _render_builtin_prompt_options(project_name, story_id)
    with tab_preview:
        _render_prompt_options_preview(context["effective_options"])
