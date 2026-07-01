"""Retrieval center page panels."""
from __future__ import annotations

import json

import streamlit as st

from memory import (
    delete_retrieval_source_file,
    list_retrieval_source_files,
    load_conflict_resolutions,
    retrieval_sources_path,
)
from retrieval import (
    RETRIEVAL_TASK_PROFILES,
    debug_retrieve_context,
    inspect_retrieval_health,
    load_retrieval_index,
    rebuild_retrieval_assets,
    retrieve_context,
)
from retrieval_eval import retrieval_profile_label
from skills import detect_potential_conflicts, save_retrieval_conflict_resolution
from ui.common import confirmed_button, scoped_widget_key
from ui.labels import (
    label_knowledge_category,
    label_retrieval_mode,
    label_scope,
    label_source_type,
)
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
    with st.expander("资料检索健康检查", expanded=True):
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
                        use_container_width=True,
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
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.caption("暂无范围统计。")
        except Exception as exc:
            st.error(f"资料检索健康检查失败：{exc}")


def _render_retrieval_source_management(project_name: str, manifest):
    with st.expander("管理已导入资料", expanded=False):
        existing_source_files = list_retrieval_source_files(project_name)
        if not existing_source_files:
            st.caption("当前没有已导入的外部资料文件。")
        else:
            selected_source_file = st.selectbox(
                "选择要删除的资料文件",
                options=existing_source_files,
                key="retrieval_source_delete_target"
            )
            st.caption("删除后会自动重建检索索引。")
            if confirmed_button(
                st,
                "删除所选资料",
                "确认删除所选资料并重建索引",
                scoped_widget_key("delete_selected_retrieval_source", project_name),
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


def _render_retrieval_hits(project_name: str, query: str):
    current_hits = st.session_state.get("retrieval_hits", [])
    for hit in current_hits:
        chunk = hit.get("chunk", {})
        st.markdown(
            f"### {label_source_type(chunk.get('source_type', 'unknown'))} / {label_scope(chunk.get('scope', 'project'))} / 检索方式={label_retrieval_mode(hit.get('retrieval_mode', 'lexical'))} / 相关度={hit.get('score', 0):.2f}"
        )
        if chunk.get("title"):
            st.caption(chunk.get("title"))
        st.write(chunk.get("content", ""))
        matched_terms = hit.get("matched_terms", [])
        if matched_terms:
            st.caption(f"命中词：{', '.join(matched_terms)}")
        expanded_terms = hit.get("expanded_terms", [])
        if expanded_terms:
            st.caption(f"查询扩展：{', '.join(expanded_terms[:12])}")
        match_reasons = hit.get("match_reasons", [])
        if match_reasons:
            st.caption("匹配原因：" + "；".join(match_reasons[:5]))
        score_breakdown = hit.get("score_breakdown", {})
        if score_breakdown:
            breakdown_text = " / ".join(f"{key}={value:.2f}" for key, value in score_breakdown.items())
            st.caption(f"分数拆解：{breakdown_text}")
        st.caption(
            f"关键词分={hit.get('lexical_score', 0):.2f} / 语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
        )

    render_retrieval_feedback_controls(project_name, current_hits, st.session_state.get("retrieval_last_query", query))
    return current_hits


def _render_retrieval_debug_payload():
    debug_payload = st.session_state.get("retrieval_debug", {})
    if not debug_payload:
        return
    with st.expander("检索调试信息", expanded=False):
        st.caption(
            f"策略={debug_payload.get('retrieval_profile') or '通用'} / 世界线={debug_payload.get('worldline_id') or '不限定'} / 模式={debug_payload.get('worldline_mode') or 'prefer'} / 检索词={', '.join(debug_payload.get('query_terms', [])) or '-'} / 候选片段={debug_payload.get('candidate_chunk_count', 0)} / 语义向量={'已启用' if debug_payload.get('semantic_enabled', False) else '未启用'}"
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
                    use_container_width=True,
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


def _render_retrieval_conflicts(project_name: str, current_hits: list[dict]):
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
                    key=f"conflict_decision_{index}",
                )
                note = st.text_area("裁决说明", height=80, key=f"conflict_note_{index}")
                if st.button("保存该冲突裁决", key=f"save_conflict_resolution_{index}"):
                    try:
                        saved = save_retrieval_conflict_resolution(project_name, conflict, decision, note)
                        st.success(f"已保存裁决：{saved.get('conflict_id', '')}")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"保存裁决失败：{exc}")

    resolutions = load_conflict_resolutions(project_name)
    if resolutions:
        with st.expander("已保存冲突裁决", expanded=False):
            st.code(json.dumps(resolutions, ensure_ascii=False, indent=2), language="json")


def _render_retrieval_preview(project_name: str, current_story_id: str, manifest):
    with st.expander("检索预览", expanded=True):
        query = st.text_area("检索查询", height=120, key="retrieval_query")
        top_k = st.slider("返回条数", min_value=1, max_value=12, value=6, key="retrieval_top_k")
        retrieval_mode = st.selectbox(
            "检索模式",
            options=["hybrid", "lexical", "semantic"],
            index=0,
            format_func=label_retrieval_mode,
            key="retrieval_mode"
        )
        retrieval_profile_options = [""] + list(RETRIEVAL_TASK_PROFILES.keys())
        retrieval_profile = st.selectbox(
            "任务策略",
            options=retrieval_profile_options,
            index=0,
            format_func=retrieval_profile_label,
            key="retrieval_task_profile",
            help="选择后会使用对应任务的来源偏好和默认匹配数量；手动来源过滤会优先于任务策略。",
        )
        scope_options = st.multiselect(
            "范围过滤",
            options=["project", "canon", "reference"],
            default=["project", "canon", "reference"],
            format_func=label_scope,
            key="retrieval_scope_filter"
        )
        source_type_candidates = sorted({chunk.source_type for chunk in manifest.chunks}) if manifest else []
        source_type_filter = st.multiselect(
            "来源类型过滤（可选）",
            options=source_type_candidates,
            default=[],
            format_func=label_source_type,
            key="retrieval_source_type_filter",
        )
        worldline_options = sorted({
            str(chunk.metadata.get("worldline_id") or "").strip()
            for chunk in manifest.chunks
            if isinstance(chunk.metadata, dict) and str(chunk.metadata.get("worldline_id") or "").strip()
        }) if manifest else []
        worldline_filter = st.selectbox(
            "世界线偏好（可选）",
            options=[""] + worldline_options,
            format_func=lambda value: "不限定" if not value else value,
            key="retrieval_worldline_filter",
            help="选择后会优先匹配同世界线资料；通用资料仍会保留。",
        )
        worldline_mode = st.selectbox(
            "世界线模式",
            options=["prefer", "strict"],
            format_func=lambda value: {"prefer": "偏好匹配", "strict": "严格过滤"}.get(value, value),
            key="retrieval_worldline_mode",
            help="偏好匹配会给同世界线资料加权、给其他世界线轻微降权；严格过滤会排除明确属于其他世界线的资料。",
        )
        include_debug = st.checkbox("生成检索调试信息", value=False, key="retrieval_include_debug")
        if st.button("执行检索"):
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
                st.session_state["retrieval_hits"] = [hit.model_dump() for hit in hits]
                st.session_state["retrieval_last_query"] = query
                st.session_state["retrieval_debug"] = debug_retrieve_context(
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

        current_hits = _render_retrieval_hits(project_name, query)
        _render_retrieval_debug_payload()
        _render_retrieval_conflicts(project_name, current_hits)


def render_retrieval_center_page(project_name: str, current_story_id: str):
    manifest = _render_retrieval_index_controls(project_name)
    _render_retrieval_health_panel(project_name)
    render_retrieval_eval_workbench(project_name, manifest)
    _render_retrieval_source_management(project_name, manifest)
    _render_retrieval_preview(project_name, current_story_id, manifest)
