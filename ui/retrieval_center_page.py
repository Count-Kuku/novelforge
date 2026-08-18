"""Retrieval center page panels."""
from __future__ import annotations

import json

import streamlit as st

from novelforge.services.memory import (
    delete_retrieval_source_file,
    list_retrieval_source_files,
    load_conflict_resolutions,
    retrieval_sources_path,
)
from novelforge.services.retrieval import (
    RETRIEVAL_TASK_PROFILES,
    debug_retrieve_context,
    inspect_retrieval_health,
    load_retrieval_index,
    rebuild_retrieval_assets,
    retrieve_context,
)
from novelforge.services.retrieval_eval import retrieval_profile_label
from novelforge.workflows.skills import detect_potential_conflicts, save_retrieval_conflict_resolution
from ui.common import confirmed_button, developer_mode_enabled, scoped_session_key, scoped_widget_key
from ui.labels import (
    label_knowledge_category,
    label_retrieval_mode,
    label_scope,
    label_source_type,
)
from ui.layout import render_empty_state, render_section_heading, render_stat_strip
from ui.retrieval_eval_panel import render_retrieval_eval_workbench
from ui.retrieval_views import render_retrieval_feedback_controls
from ui.step_views import render_step_json_expander


DECISION_LABELS = {
    "merge": "人工折中",
    "use_project": "采纳项目设定",
    "use_external": "采纳外部/原作资料",
    "ignore": "忽略该冲突",
}

SEVERITY_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}


def _render_retrieval_index_controls(project_name: str):
    manifest = None
    try:
        manifest = load_retrieval_index(project_name)
        st.caption(
            f"当前索引：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 构建时间 {manifest.built_at} / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'} / 模型={manifest.embedding_model or '-'}"
        )
    except Exception as exc:
        st.warning(f"索引读取失败：{exc}")

    col1, col2, col3 = st.columns(3)
    if col1.button("重建关键词索引"):
        with st.spinner("正在重建关键词索引..."):
            manifest = rebuild_retrieval_assets(project_name, build_vectors=False)
        st.success(
            f"关键词索引已重建：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段"
        )
        st.rerun()
    if col2.button("重建完整索引"):
        with st.spinner("正在重建索引和语义向量..."):
            manifest = rebuild_retrieval_assets(project_name, build_vectors=True)
        st.success(
            f"索引已重建：{manifest.document_count} 份文档 / {manifest.chunk_count} 个片段 / 语义向量={'已启用' if manifest.embedding_enabled else '未启用'}"
        )
        st.rerun()

    source_dir = retrieval_sources_path(project_name)
    col3.caption(f"外部资料目录：`{source_dir}`")
    return manifest


def _render_retrieval_health_panel(project_name: str):
    render_section_heading("索引健康", "检查资料是否已完整编入关键词和语义索引。")
    with st.container(border=True):
        try:
            health = inspect_retrieval_health(project_name)
            status_label = {
                "healthy": "健康",
                "warning": "需要注意",
                "error": "异常",
            }.get(health.get("status", ""), health.get("status", "未知"))
            st.caption(
                f"状态：{status_label} / 索引构建时间：{health.get('built_at') or '-'} / "
                f"向量构建时间：{health.get('vector_built_at') or '-'} / "
                f"当前向量模型：{health.get('active_embedding_model') or '-'}"
            )
            metric_cols = st.columns(6)
            metric_cols[0].metric("索引文档", health.get("document_count", 0))
            metric_cols[1].metric("索引片段", health.get("chunk_count", 0))
            metric_cols[2].metric("当前片段", health.get("current_chunk_count", 0))
            metric_cols[3].metric("向量数", health.get("vector_count", 0))
            metric_cols[4].metric("缺失向量", health.get("missing_vector_count", 0))
            metric_cols[5].metric("陈旧片段", health.get("stale_chunk_count", 0))

            if health.get("embedding_enabled"):
                st.success(f"语义向量已启用：{health.get('vector_model') or health.get('embedding_model') or '-'} / 维度 {health.get('vector_dimension') or '-'}")
                build_mode_label = "增量复用" if health.get("vector_build_mode") == "incremental" else "完整生成"
                st.caption(
                    f"最近向量构建：{build_mode_label} / 复用 {health.get('reused_vector_count', 0)} / "
                    f"新生成 {health.get('generated_vector_count', 0)} / 移除旧向量 {health.get('removed_vector_count', 0)}"
                )
            else:
                st.warning("语义向量未启用。混合检索会自动退回关键词检索；如需语义匹配，请配置可用的 Embedding 模型后重建完整索引。")

            for issue in health.get("issues", []):
                severity = issue.get("severity")
                message = issue.get("message", "")
                if severity == "high":
                    st.error(message)
                elif severity == "medium":
                    st.warning(message)
                else:
                    st.info(message)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("#### 来源分布")
                source_counts = health.get("source_type_counts", {})
                if source_counts:
                    st.dataframe(
                        [{"来源类型": label_source_type(key), "片段数": value} for key, value in source_counts.items()],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.caption("暂无来源片段。")
            with col_b:
                st.markdown("#### 范围分布")
                scope_counts = health.get("scope_counts", {})
                if scope_counts:
                    st.dataframe(
                        [{"范围": label_scope(key), "片段数": value} for key, value in scope_counts.items()],
                        width="stretch",
                        hide_index=True,
                    )
                else:
                    st.caption("暂无范围统计。")
        except Exception as exc:
            st.error(f"资料检索健康检查失败：{exc}")


def _render_retrieval_source_management(project_name: str, manifest):
    render_section_heading("索引来源", "查看索引中的资料，或删除不再需要的原文。")
    with st.container(border=True):
        existing_source_files = list_retrieval_source_files(project_name)
        if not existing_source_files:
            st.caption("当前没有已导入的外部资料文件。")
        else:
            selected_source_file = st.selectbox(
                "选择要删除的资料文件",
                options=existing_source_files,
                key=scoped_widget_key("retrieval_source_delete_target", project_name),
            )
            st.caption("删除后会自动重建检索索引。")
            if confirmed_button(
                st,
                "删除所选资料",
                "确认删除所选资料并重建索引",
                scoped_widget_key("delete_selected_retrieval_source", project_name, selected_source_file),
            ):
                try:
                    deleted = delete_retrieval_source_file(project_name, selected_source_file)
                    if deleted:
                        rebuild_retrieval_assets(project_name, build_vectors=True)
                        st.success(f"已删除资料：{selected_source_file}")
                        st.rerun()
                    else:
                        st.warning("目标资料不存在，可能已被删除。")
                except Exception as exc:
                    st.error(f"删除资料失败：{exc}")
        if manifest and manifest.documents:
            with st.expander("索引来源预览", expanded=False):
                for doc in manifest.documents[:30]:
                    st.markdown(f"- `{label_source_type(doc.source_type)}` / `{label_scope(doc.scope)}` / `{doc.title or doc.doc_id}`")
                if len(manifest.documents) > 30:
                    st.caption(f"仅显示前 30 项，共 {len(manifest.documents)} 项。")


def _render_retrieval_hits(project_name: str, current_story_id: str, query: str):
    hits_key = scoped_session_key("retrieval_hits", project_name, current_story_id)
    query_key = scoped_session_key("retrieval_last_query", project_name, current_story_id)
    current_hits = st.session_state.get(hits_key, [])
    if not current_hits and st.session_state.get(query_key):
        render_empty_state("未找到匹配资料", "可以尝试缩短查询、取消范围限制，或重建完整索引。")
    for rank, hit in enumerate(current_hits, start=1):
        chunk = hit.get("chunk", {})
        with st.container(border=True):
            st.markdown(f"#### {rank}. {chunk.get('title') or '未命名资料'}")
            st.caption(
                f"{label_source_type(chunk.get('source_type', 'unknown'))} · "
                f"{label_scope(chunk.get('scope', 'project'))} · "
                f"相关度 {hit.get('score', 0):.2f}"
            )
            st.write(chunk.get("content", ""))
            matched_terms = hit.get("matched_terms", [])
            if matched_terms:
                st.caption(f"命中词：{', '.join(matched_terms[:12])}")
            with st.expander("为什么匹配到这条资料", expanded=False):
                match_reasons = hit.get("match_reasons", [])
                if match_reasons:
                    st.caption("匹配原因：" + "；".join(match_reasons[:5]))
                st.caption(
                    f"方式={label_retrieval_mode(hit.get('retrieval_mode', 'lexical'))} / "
                    f"关键词分={hit.get('lexical_score', 0):.2f} / "
                    f"语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
                )

    render_retrieval_feedback_controls(
        project_name,
        current_hits,
        st.session_state.get(query_key, query),
        story_id=current_story_id,
    )
    return current_hits


def _render_retrieval_debug_payload(project_name: str, current_story_id: str):
    debug_key = scoped_session_key("retrieval_debug", project_name, current_story_id)
    debug_payload = st.session_state.get(debug_key, {})
    if not debug_payload:
        return
    with st.expander("检索调试信息", expanded=False):
        st.caption(
            f"匹配策略={debug_payload.get('retrieval_profile') or '通用'} / 资料版本={debug_payload.get('worldline_id') or '不限定'} / 版本处理={debug_payload.get('worldline_mode') or 'prefer'} / 匹配词={', '.join(debug_payload.get('query_terms', [])) or '-'} / 候选片段={debug_payload.get('candidate_chunk_count', 0)} / 语义向量={'已启用' if debug_payload.get('semantic_enabled', False) else '未启用'}"
        )
        expanded_terms = debug_payload.get("expanded_terms", [])
        if expanded_terms:
            st.caption(f"查询扩展：{', '.join(expanded_terms[:20])}")
        alias_groups = debug_payload.get("matched_alias_groups", [])
        if alias_groups:
            with st.expander("命中的别名组", expanded=False):
                st.dataframe(
                    [
                        {
                            "主名称": group.get("canonical_name", ""),
                            "命中名称": "、".join(group.get("matched_names", [])),
                            "别名": "、".join(group.get("aliases", [])),
                            "分类": label_knowledge_category(group.get("category", "")),
                        }
                        for group in alias_groups
                    ],
                    width="stretch",
                    hide_index=True,
                )
        st.markdown("### 重排前")
        for index, hit in enumerate(debug_payload.get("initial_hits", []), start=1):
            chunk = hit.get("chunk", {})
            st.caption(f"{index}. {label_source_type(chunk.get('source_type', 'unknown'))} / {chunk.get('title', '')} / 相关度={hit.get('score', 0):.2f}")
        st.markdown("### 重排后")
        for index, hit in enumerate(debug_payload.get("reranked_hits", []), start=1):
            chunk = hit.get("chunk", {})
            st.caption(f"{index}. {label_source_type(chunk.get('source_type', 'unknown'))} / {chunk.get('title', '')} / 相关度={hit.get('score', 0):.2f}")
        render_step_json_expander("完整调试详细数据", debug_payload)


def _render_retrieval_conflicts(project_name: str, current_story_id: str, current_hits: list[dict]):
    conflicts = detect_potential_conflicts(current_hits)
    if conflicts:
        st.markdown("### 检索冲突裁决")
        for index, conflict in enumerate(conflicts, start=1):
            project_chunk = conflict.get("project_hit", {}).get("chunk", {})
            external_chunk = conflict.get("external_hit", {}).get("chunk", {})
            severity = SEVERITY_LABELS.get(conflict.get("severity", "low"), conflict.get("severity", "low"))
            with st.expander(f"冲突 {index} / 严重程度={severity}", expanded=False):
                st.caption(f"共同命中词：{', '.join(conflict.get('shared_terms', [])) or '-'}")
                st.markdown(f"**项目证据**：{label_source_type(project_chunk.get('source_type', 'unknown'))} / {project_chunk.get('title', '未命名')}")
                st.write(project_chunk.get("content", ""))
                st.markdown(f"**外部证据**：{label_source_type(external_chunk.get('source_type', 'unknown'))} / {external_chunk.get('title', '未命名')}")
                st.write(external_chunk.get("content", ""))
                decision = st.selectbox(
                    "裁决",
                    options=["merge", "use_project", "use_external", "ignore"],
                    format_func=lambda value: DECISION_LABELS.get(value, value),
                    key=scoped_widget_key("conflict_decision", project_name, current_story_id, index),
                )
                note = st.text_area(
                    "裁决说明",
                    height=80,
                    key=scoped_widget_key("conflict_note", project_name, current_story_id, index),
                )
                if st.button(
                    "保存该冲突裁决",
                    key=scoped_widget_key("save_conflict_resolution", project_name, current_story_id, index),
                ):
                    try:
                        saved = save_retrieval_conflict_resolution(
                            project_name,
                            conflict,
                            decision,
                            note,
                            story_id=current_story_id,
                        )
                        st.success(f"已保存裁决：{saved.get('conflict_id', '')}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"保存裁决失败：{exc}")

    resolutions = load_conflict_resolutions(project_name)
    if resolutions and developer_mode_enabled():
        with st.expander("已保存冲突裁决", expanded=False):
            st.code(json.dumps(resolutions, ensure_ascii=False, indent=2), language="json")


def _render_retrieval_preview(project_name: str, current_story_id: str, manifest):
    state_scope = (project_name, current_story_id)
    hits_key = scoped_session_key("retrieval_hits", *state_scope)
    last_query_key = scoped_session_key("retrieval_last_query", *state_scope)
    debug_key = scoped_session_key("retrieval_debug", *state_scope)
    render_section_heading("查找资料", "用一个具体问题测试写作时能否准确取回相关知识。")
    with st.container(border=True):
        query = st.text_area(
            "检索查询",
            height=120,
            key=scoped_widget_key("retrieval_query", *state_scope),
        )
        top_k = st.slider(
            "返回条数",
            min_value=1,
            max_value=12,
            value=6,
            key=scoped_widget_key("retrieval_top_k", *state_scope),
        )
        retrieval_mode = st.selectbox(
            "检索模式",
            options=["hybrid", "lexical", "semantic"],
            index=0,
            format_func=label_retrieval_mode,
            key=scoped_widget_key("retrieval_mode", *state_scope),
        )
        retrieval_profile_options = [""] + list(RETRIEVAL_TASK_PROFILES.keys())
        retrieval_profile = st.selectbox(
            "使用场景",
            options=retrieval_profile_options,
            index=0,
            format_func=retrieval_profile_label,
            key=scoped_widget_key("retrieval_task_profile", *state_scope),
            help="选择后会使用对应任务的来源偏好和默认匹配数量；手动来源过滤会优先于任务策略。",
        )
        scope_options = st.multiselect(
            "范围过滤",
            options=["project", "canon", "reference"],
            default=["project", "canon", "reference"],
            format_func=label_scope,
            key=scoped_widget_key("retrieval_scope_filter", *state_scope),
        )
        source_type_candidates = sorted({chunk.source_type for chunk in manifest.chunks}) if manifest else []
        source_type_filter = st.multiselect(
            "来源类型过滤（可选）",
            options=source_type_candidates,
            default=[],
            format_func=label_source_type,
            key=scoped_widget_key("retrieval_source_type_filter", *state_scope),
        )
        worldline_options = sorted({
            str(chunk.metadata.get("worldline_id") or "").strip()
            for chunk in manifest.chunks
            if isinstance(chunk.metadata, dict) and str(chunk.metadata.get("worldline_id") or "").strip()
        }) if manifest else []
        worldline_filter = st.selectbox(
            "优先使用的资料版本（可选）",
            options=[""] + worldline_options,
            format_func=lambda value: "不限定" if not value else value,
            key=scoped_widget_key("retrieval_worldline_filter", *state_scope),
            help="选择后会优先匹配同一主线、平行世界或剧情分支的资料；通用资料仍会保留。",
        )
        worldline_mode = st.selectbox(
            "跨版本资料处理",
            options=["prefer", "strict"],
            format_func=lambda value: {"prefer": "优先当前版本（推荐）", "strict": "只用当前版本"}.get(value, value),
            key=scoped_widget_key("retrieval_worldline_mode", *state_scope),
            help="“优先当前版本”仍允许使用通用资料；“只用当前版本”会排除明确属于其他版本的内容。",
        )
        include_debug = st.checkbox(
            "显示详细匹配信息",
            value=False,
            key=scoped_widget_key("retrieval_include_debug", *state_scope),
        )
        if st.button("查找匹配资料", key=scoped_widget_key("run_retrieval", *state_scope), type="primary", width="stretch"):
            try:
                hits = retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    allowed_source_types=source_type_filter or None,
                    retrieval_mode=retrieval_mode,
                    retrieval_profile=retrieval_profile or None,
                    worldline_id=worldline_filter or None,
                    worldline_mode=worldline_mode,
                    story_id=current_story_id,
                )
                st.session_state[hits_key] = [hit.model_dump() for hit in hits]
                st.session_state[last_query_key] = query
                st.session_state[debug_key] = debug_retrieve_context(
                    project_name,
                    query,
                    top_k=top_k,
                    allowed_scopes=scope_options,
                    allowed_source_types=source_type_filter or None,
                    retrieval_mode=retrieval_mode,
                    retrieval_profile=retrieval_profile or None,
                    worldline_id=worldline_filter or None,
                    worldline_mode=worldline_mode,
                    story_id=current_story_id,
                ) if include_debug else {}
            except Exception as exc:
                st.error(f"检索失败：{exc}")

        current_hits = _render_retrieval_hits(project_name, current_story_id, query)
        _render_retrieval_debug_payload(project_name, current_story_id)
        _render_retrieval_conflicts(project_name, current_story_id, current_hits)


def render_retrieval_center_page(project_name: str, current_story_id: str):
    view_key = scoped_widget_key("retrieval_center_view", project_name, current_story_id)
    view = st.segmented_control(
        "资料检索视图",
        options=["查找资料", "质量评测", "索引维护"],
        default="查找资料" if view_key not in st.session_state else None,
        key=view_key,
        label_visibility="collapsed",
    )
    manifest = None
    try:
        manifest = load_retrieval_index(project_name)
    except Exception:
        pass
    if view == "查找资料":
        _render_retrieval_preview(project_name, current_story_id, manifest)
    elif view == "质量评测":
        render_retrieval_eval_workbench(project_name, current_story_id, manifest)
    else:
        manifest = _render_retrieval_index_controls(project_name)
        _render_retrieval_health_panel(project_name)
        _render_retrieval_source_management(project_name, manifest)
