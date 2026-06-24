"""Reusable renderers for workflow step outputs."""
from __future__ import annotations

import json

import streamlit as st

from retrieval_eval import build_retrieval_usage_report_from_payload
from ui.labels import label_authority, label_schema, label_scope, label_source_type
from ui.retrieval_views import render_retrieval_hits_block

def render_step_status_message(step_result: dict, success_message: str, failure_prefix: str):
    if not step_result:
        return

    status = step_result.get("status")
    if status == "completed":
        st.success(success_message)
    elif status == "skipped":
        warnings = step_result.get("warnings") or []
        st.info(warnings[0] if warnings else "步骤已跳过。")
    else:
        st.error(f"{failure_prefix}{step_result.get('error', '未知错误')}")

def render_step_validation(step_result: dict):
    validation = step_result.get("validation", {})
    if validation.get("status") == "passed":
        st.caption(f"结构校验通过：{label_schema(validation.get('schema_name', '-'))}")
    elif validation.get("status") == "failed":
        schema_name = label_schema(validation.get("schema_name", "-"))
        errors = validation.get("errors") or []
        message = errors[0] if errors else validation.get("message", "结构校验失败。")
        st.caption(f"结构校验失败：{schema_name} / {message}")

def render_step_json_expander(title: str, payload: dict):
    if not payload:
        return
    with st.expander(title, expanded=False):
        st.code(json.dumps(payload, ensure_ascii=False, indent=2), language="json")

def render_retrieval_usage_report(hits: list[dict], title: str = "资料使用报告"):
    report = build_retrieval_usage_report_from_payload(
        hits,
        label_source_type_func=label_source_type,
        label_scope_func=label_scope,
        label_authority_func=label_authority,
    )
    with st.expander(title, expanded=bool(hits)):
        metric_cols = st.columns(4)
        metric_cols[0].metric("召回片段", report.get("hit_count", 0))
        metric_cols[1].metric("来源类型", len(report.get("source_type_counts", {})))
        metric_cols[2].metric("硬约束/设定", len(report.get("constraints", [])))
        metric_cols[3].metric("冲突裁决", len(report.get("conflicts", [])))
        if report.get("scope_counts"):
            st.caption("范围分布：" + " / ".join(f"{label_scope(key)}={value}" for key, value in report.get("scope_counts", {}).items()))
        if report.get("source_type_counts"):
            st.caption("来源分布：" + " / ".join(f"{label_source_type(key)}={value}" for key, value in report.get("source_type_counts", {}).items()))
        if report.get("risk_notes"):
            for note in report.get("risk_notes", []):
                st.info(note)
        priority_sources = report.get("priority_sources", [])
        if priority_sources:
            st.markdown("#### 优先参考资料")
            st.dataframe(priority_sources, use_container_width=True, hide_index=True)
        constraints = report.get("constraints", [])
        if constraints:
            st.markdown("#### 需要优先遵守的约束/设定")
            for item in constraints:
                st.markdown(f"**{item.get('来源', '')}**")
                st.caption(item.get("内容", ""))
        conflicts = report.get("conflicts", [])
        if conflicts:
            st.markdown("#### 已保存冲突裁决")
            for item in conflicts:
                st.markdown(f"**{item.get('来源', '')}**")
                st.caption(item.get("内容", ""))


def render_step_retrieval(step_result: dict, title: str, fallback_hits: list[dict] | None = None):
    hits = step_result.get("retrieval_hits", []) if step_result else []
    active_hits = hits or (fallback_hits or [])
    if not active_hits:
        return
    render_retrieval_usage_report(active_hits, "本次生成资料使用报告")
    render_retrieval_hits_block(active_hits, title)

