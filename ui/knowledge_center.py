"""Paged unified source and knowledge browser for the ingestion center."""

from __future__ import annotations

import html
import json

import streamlit as st

from novelforge.services.memory import (
    knowledge_revision_diff,
    load_source_revisions,
    load_knowledge_center_index_state,
    load_knowledge_center_record,
    load_knowledge_evidence,
    load_knowledge_revisions,
    restore_knowledge_revision,
    restore_archived_knowledge_item,
    retry_knowledge_center_index,
    search_knowledge_center,
)
from ui.common import scoped_widget_key
from ui.labels import label_knowledge_category


VIEW_FILTERS = {
    "全部": {},
    "角色": {"record_types": ["knowledge"], "categories": ["characters"]},
    "世界观": {"record_types": ["knowledge"], "categories": ["world_rules"]},
    "时间线": {"record_types": ["knowledge"], "categories": ["timeline_events"]},
    "关系": {"record_types": ["knowledge"], "categories": ["relationships"]},
    "地点与组织": {"record_types": ["knowledge"], "categories": ["locations", "organizations"]},
    "来源": {"record_types": ["source"]},
    "待审核": {"record_types": ["pending"]},
    "归档": {"archived_only": True, "include_archived": True},
}


def _cursor_stack_key(project_name: str, story_id: str) -> str:
    return scoped_widget_key("knowledge_center_cursor_stack", project_name, story_id)


def _selected_key(project_name: str, story_id: str) -> str:
    return scoped_widget_key("knowledge_center_selected", project_name, story_id)


def _render_index_state(project_name: str) -> None:
    state = load_knowledge_center_index_state(project_name)
    status = str(state.get("retrieval_status") or "completed")
    counts = state.get("job_counts") if isinstance(state.get("job_counts"), dict) else {}
    labels = {
        "queued": "检索索引等待后台更新",
        "running": "检索索引正在后台更新",
        "completed": "检索索引已是最新",
        "failed": "检索索引更新失败",
    }
    st.caption(
        f"{labels.get(status, status)} · 待处理 {int(counts.get('queued') or 0)} · "
        f"失败 {int(counts.get('failed') or 0)}"
    )
    failed_count = int(counts.get("failed") or 0)
    if (status == "failed" or failed_count) and st.button(
        "重试索引更新", key=scoped_widget_key("knowledge_center_retry_index", project_name),
    ):
        retry_knowledge_center_index(project_name)
        st.rerun()


def _plain_snippet(value: str) -> str:
    # The service emits only mark tags; escape every other character before
    # re-enabling those two tags for safe highlighting.
    escaped = html.escape(str(value or ""))
    return escaped.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")


def _render_result_list(project_name: str, story_id: str, items: list[dict]) -> None:
    selected_key = _selected_key(project_name, story_id)
    if not items:
        st.info("当前视图没有匹配内容。")
        return
    for item in items:
        record_type = str(item.get("record_type") or "")
        record_id = str(item.get("record_id") or "")
        category = str(item.get("category") or "")
        label = {
            "knowledge": label_knowledge_category(category),
            "pending": "待审核",
            "source": "来源",
        }.get(record_type, record_type)
        with st.container(border=True):
            st.caption(f"{label} · {item.get('record_status') or '-'}")
            st.markdown(f"**{item.get('title') or record_id}**")
            st.markdown(_plain_snippet(str(item.get("snippet") or "")), unsafe_allow_html=True)
            if st.button(
                "打开详情",
                key=scoped_widget_key("knowledge_center_open", project_name, story_id, record_type, record_id),
            ):
                st.session_state[selected_key] = {"record_type": record_type, "record_id": record_id}
                st.rerun()


def _source_text(record: dict) -> str:
    if str(record.get("indexed_text") or "").strip():
        return str(record.get("indexed_text") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    for key in ("content", "text", "raw_text", "source_text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return str(record.get("summary") or "")


def _highlight_source(text: str, query: str) -> str:
    escaped = html.escape(str(text or ""))
    terms = [term for term in str(query or "").split() if term]
    for term in sorted(set(terms), key=len, reverse=True):
        safe = html.escape(term)
        escaped = escaped.replace(safe, f"<mark>{safe}</mark>")
    return escaped


def _render_source_detail(record: dict, query: str) -> None:
    st.caption(
        f"{record.get('source_title') or '-'} · {record.get('source_type') or '-'} · "
        f"修订 {record.get('source_revision_id') or '-'} · "
        f"位置 {record.get('start_offset', '-')}-{record.get('end_offset', '-')}"
    )
    text = _source_text(record)
    if text:
        st.markdown(
            f"<div style='white-space:pre-wrap'>{_highlight_source(text, query)}</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("该来源当前只保存了结构元数据，原文文件可从资料批次打开。")
    revisions = record.get("_source_revisions") or []
    if revisions:
        st.dataframe(revisions, width="stretch", hide_index=True)


def _render_knowledge_history(project_name: str, record: dict) -> None:
    knowledge_id = str(record.get("knowledge_id") or "")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    revisions = load_knowledge_revisions(project_name, knowledge_id)
    evidence = load_knowledge_evidence(project_name, knowledge_id)
    if evidence:
        st.markdown("##### 来源证据")
        st.dataframe([
            {
                "状态": item.get("validation_status") or "",
                "引文": str(item.get("quote") or "")[:240],
                "来源": item.get("source_id") or "",
                "位置": f"{item.get('start_offset', '-')}-{item.get('end_offset', '-')}",
            }
            for item in evidence
        ], width="stretch", hide_index=True)
    if not revisions:
        return
    st.markdown("##### 修订历史")
    options = [str(item.get("revision_id") or "") for item in revisions]
    selected = st.selectbox(
        "选择历史修订",
        options=options,
        format_func=lambda revision_id: next(
            (
                f"版本 {item.get('revision_no')} · {item.get('created_at') or '-'} · {item.get('reason') or '无备注'}"
                for item in revisions if str(item.get("revision_id") or "") == revision_id
            ), revision_id,
        ),
        key=scoped_widget_key("knowledge_center_revision", project_name, knowledge_id),
    )
    revision = next(item for item in revisions if str(item.get("revision_id") or "") == selected)
    diff = knowledge_revision_diff(payload, revision)
    st.code(diff or "该修订与当前版本没有字段差异。", language="diff")
    if st.button(
        "恢复为新修订",
        key=scoped_widget_key("knowledge_center_restore_revision", project_name, knowledge_id, selected),
    ):
        restore_knowledge_revision(project_name, knowledge_id, selected)
        st.success("已恢复历史内容，并保留当前版本和完整修订链。")
        st.rerun()


def _render_detail(project_name: str, story_id: str, query: str) -> None:
    selection = st.session_state.get(_selected_key(project_name, story_id))
    if not isinstance(selection, dict):
        st.info("从左侧结果打开一条内容后，这里会显示详情和可用操作。")
        return
    record_type = str(selection.get("record_type") or "")
    record_id = str(selection.get("record_id") or "")
    record = load_knowledge_center_record(project_name, record_type, record_id)
    if not record:
        st.warning("该内容已经不存在。")
        return
    title = record.get("name") or record.get("title") or record.get("source_title") or record_id
    st.markdown(f"### {title}")
    if record_type == "source":
        record["_source_revisions"] = load_source_revisions(project_name, str(record.get("source_id") or ""))
        _render_source_detail(record, query)
        return
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    st.caption(
        f"{label_knowledge_category(record.get('category') or '')} · "
        f"故事 {record.get('story_id') or '项目共享'} · 世界线 {record.get('worldline_id') or '通用'}"
    )
    if payload.get("summary"):
        st.write(payload.get("summary"))
    if payload.get("typed_data"):
        st.dataframe(
            [{"字段": key, "内容": value} for key, value in payload["typed_data"].items()],
            width="stretch", hide_index=True,
        )
    if record_type == "knowledge" and record.get("archived"):
        if st.button(
            "恢复归档条目",
            key=scoped_widget_key("knowledge_center_restore_archive", project_name, record_id),
        ):
            restore_archived_knowledge_item(project_name, record_id)
            st.success("已恢复归档知识，并追加恢复修订。")
            st.rerun()
    if record_type == "knowledge":
        _render_knowledge_history(project_name, record)
    else:
        st.caption("待审核条目请在“审核”工作区使用规范表单确认、编辑或归档。")


def render_unified_knowledge_center(project_name: str, story_id: str) -> None:
    st.markdown("### 资料与知识中心")
    st.caption("跨来源、分类、故事与世界线搜索；结果按页加载，不会一次创建全部控件。")
    _render_index_state(project_name)
    view = st.segmented_control(
        "统一视图", options=list(VIEW_FILTERS), default="全部",
        key=scoped_widget_key("knowledge_center_view", project_name, story_id),
    ) or "全部"
    query = st.text_input(
        "搜索资料和知识",
        placeholder="名称、摘要、原文、来源或标签",
        key=scoped_widget_key("knowledge_center_query", project_name, story_id),
    )
    worldline = st.text_input(
        "世界线（留空不过滤）", value="",
        key=scoped_widget_key("knowledge_center_worldline", project_name, story_id),
    )
    signature = json.dumps([view, query, worldline], ensure_ascii=False)
    stack_key = _cursor_stack_key(project_name, story_id)
    stack_state = st.session_state.get(stack_key)
    if not isinstance(stack_state, dict) or stack_state.get("signature") != signature:
        stack_state = {"signature": signature, "cursors": [""]}
        st.session_state[stack_key] = stack_state
    cursors = list(stack_state.get("cursors") or [""])
    current_cursor = cursors[-1]
    filters = dict(VIEW_FILTERS.get(view) or {})
    result = search_knowledge_center(
        project_name,
        query=query,
        story_id=story_id,
        worldline_id=worldline or None,
        cursor=current_cursor,
        page_size=30,
        **filters,
    )
    list_col, detail_col = st.columns([1, 1.25])
    with list_col:
        st.caption(f"本页 {len(result.get('items') or [])} 条")
        _render_result_list(project_name, story_id, result.get("items") or [])
        prev_col, next_col = st.columns(2)
        if prev_col.button("上一页", disabled=len(cursors) <= 1, width="stretch"):
            cursors.pop()
            st.session_state[stack_key] = {"signature": signature, "cursors": cursors}
            st.rerun()
        if next_col.button("下一页", disabled=not result.get("has_more"), width="stretch"):
            cursors.append(str(result.get("next_cursor") or ""))
            st.session_state[stack_key] = {"signature": signature, "cursors": cursors}
            st.rerun()
    with detail_col:
        _render_detail(project_name, story_id, query)
