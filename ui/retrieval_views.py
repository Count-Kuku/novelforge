"""Shared retrieval result renderers."""
from __future__ import annotations

import streamlit as st

from memory import append_retrieval_feedback
from skills import detect_potential_conflicts
from ui.labels import label_authority, label_retrieval_mode, label_scope, label_source_type


SEVERITY_LABELS = {
    "low": "?",
    "medium": "?",
    "high": "?",
}

def render_retrieval_hits_block(hits: list[dict], title: str):
    if not hits:
        return

    with st.expander(title, expanded=False):
        grouped = {"project": {}, "canon": {}, "reference": {}}
        for hit in hits:
            chunk = hit.get("chunk", {})
            scope = chunk.get("scope", "project") or "project"
            source_type = chunk.get("source_type", "unknown") or "unknown"
            grouped.setdefault(scope, {}).setdefault(source_type, []).append(hit)

        hit_index = 1
        for scope in ["project", "canon", "reference"]:
            source_groups = grouped.get(scope, {})
            if not source_groups:
                continue
            st.markdown(f"## {label_scope(scope)}")
            for source_type, source_hits in source_groups.items():
                st.markdown(f"### {label_source_type(source_type)}")
                for hit in source_hits:
                    chunk = hit.get("chunk", {})
                    st.markdown(
                        f"#### [{hit_index}] 检索方式={label_retrieval_mode(hit.get('retrieval_mode', 'lexical'))} / 相关度={hit.get('score', 0):.2f}"
                    )
                    if chunk.get("title"):
                        st.caption(chunk.get("title"))
                    matched_terms = hit.get("matched_terms", [])
                    authority = label_authority(chunk.get("metadata", {}).get("authority", "unknown"))
                    if matched_terms:
                        st.caption(f"命中词：{', '.join(matched_terms)}")
                    expanded_terms = hit.get("expanded_terms", [])
                    if expanded_terms:
                        st.caption(f"查询扩展：{', '.join(expanded_terms[:12])}")
                    match_reasons = hit.get("match_reasons", [])
                    if match_reasons:
                        st.caption("召回原因：" + "；".join(match_reasons[:5]))
                    score_breakdown = hit.get("score_breakdown", {})
                    if score_breakdown:
                        breakdown_text = " / ".join(f"{key}={value:.2f}" for key, value in score_breakdown.items())
                        st.caption(f"分数拆解：{breakdown_text}")
                    st.caption(
                        f"可信度={authority} / 关键词分={hit.get('lexical_score', 0):.2f} / 语义分={hit.get('semantic_score', 0):.2f} / 来源={chunk.get('path', '-') }"
                    )
                    st.write(chunk.get("content", ""))
                    hit_index += 1

        potential_conflicts = detect_potential_conflicts(hits)
        if potential_conflicts:
            st.markdown("## 潜在冲突")
            for index, conflict in enumerate(potential_conflicts, start=1):
                shared_terms = ", ".join(conflict.get("shared_terms", [])) or "(无)"
                project_chunk = conflict.get("project_hit", {}).get("chunk", {})
                external_chunk = conflict.get("external_hit", {}).get("chunk", {})
                project_authority = label_authority(conflict.get("project_authority", project_chunk.get("metadata", {}).get("authority", "project")))
                external_authority = label_authority(conflict.get("external_authority", external_chunk.get("metadata", {}).get("authority", "unknown")))
                severity = SEVERITY_LABELS.get(conflict.get("severity", "low"), conflict.get("severity", "low"))
                rationale = conflict.get("rationale", "")
                st.markdown(f"### [{index}] 严重程度={severity} / 共同命中词={shared_terms}")
                st.caption(
                    f"项目资料：{label_source_type(project_chunk.get('source_type', 'unknown'))} / {project_chunk.get('title', '未命名')} / 可信度={project_authority}"
                )
                st.caption(
                    f"外部资料：{label_scope(external_chunk.get('scope', 'reference'))} / {label_source_type(external_chunk.get('source_type', 'unknown'))} / {external_chunk.get('title', '未命名')} / 可信度={external_authority}"
                )
                if rationale:
                    st.caption(f"判断理由：{rationale}")


def render_retrieval_feedback_controls(project_name: str, current_hits: list[dict], query: str):
    if not current_hits:
        return
    with st.expander("记录本次检索反馈", expanded=False):
        st.caption("反馈会保存到项目 RAG 资产中；后续检索会对有用/优先片段加权，对无用/错误片段降权。")
        hit_options = [
            str(hit.get("chunk", {}).get("chunk_id") or "")
            for hit in current_hits
            if hit.get("chunk", {}).get("chunk_id")
        ]
        selected_chunk_id = st.selectbox(
            "选择片段",
            options=hit_options,
            format_func=lambda value: next(
                (
                    f"{label_source_type(hit.get('chunk', {}).get('source_type', ''))} / "
                    f"{hit.get('chunk', {}).get('title', '') or value} / score={hit.get('score', 0):.2f}"
                    for hit in current_hits
                    if hit.get("chunk", {}).get("chunk_id") == value
                ),
                value,
            ),
            key="retrieval_feedback_chunk",
        )
        rating = st.radio(
            "反馈类型",
            options=["helpful", "priority", "irrelevant", "wrong"],
            horizontal=True,
            format_func=lambda value: {
                "helpful": "有用",
                "priority": "应优先",
                "irrelevant": "无关",
                "wrong": "错误",
            }.get(value, value),
            key="retrieval_feedback_rating",
        )
        note = st.text_area("反馈备注（可选）", height=70, key="retrieval_feedback_note")
        if st.button("保存检索反馈", key="save_retrieval_feedback", use_container_width=True):
            selected_hit = next((hit for hit in current_hits if hit.get("chunk", {}).get("chunk_id") == selected_chunk_id), {})
            chunk = selected_hit.get("chunk", {})
            try:
                saved = append_retrieval_feedback(project_name, {
                    "query": query,
                    "rating": rating,
                    "note": note,
                    "chunk_id": chunk.get("chunk_id", ""),
                    "document_id": chunk.get("document_id", ""),
                    "source_type": chunk.get("source_type", ""),
                    "scope": chunk.get("scope", ""),
                    "title": chunk.get("title", ""),
                    "path": chunk.get("path", ""),
                })
                st.success(f"已保存反馈：{saved.get('rating')} / {saved.get('title') or saved.get('chunk_id')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存反馈失败：{exc}")

