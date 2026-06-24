"""RAG evaluation workbench panel."""
from __future__ import annotations

import streamlit as st

from memory import (
    delete_retrieval_eval_case,
    load_retrieval_eval_cases,
    load_retrieval_eval_runs,
    load_retrieval_feedback,
    upsert_retrieval_eval_case,
)
from retrieval import RETRIEVAL_TASK_PROFILES
from retrieval_eval import (
    parse_multiline_or_comma_values,
    retrieval_profile_label,
    run_retrieval_eval_cases,
)
from ui.common import confirmed_button, scoped_widget_key
from ui.labels import label_retrieval_mode, label_scope, label_source_type
from ui.step_views import render_step_json_expander


def _load_eval_workbench_state(project_name: str, manifest) -> tuple[list[dict], list[dict], list[dict], list[str]]:
    cases = load_retrieval_eval_cases(project_name)
    runs = list(reversed(load_retrieval_eval_runs(project_name)))
    feedback_items = load_retrieval_feedback(project_name)
    source_type_candidates = sorted({chunk.source_type for chunk in manifest.chunks}) if manifest else []
    return cases, runs, feedback_items, source_type_candidates


def _render_eval_metrics(cases: list[dict], runs: list[dict], feedback_items: list[dict]) -> None:
    metric_cols = st.columns(4)
    active_cases = [case for case in cases if str(case.get("status") or "active") == "active"]
    metric_cols[0].metric("评测用例", len(cases))
    metric_cols[1].metric("启用用例", len(active_cases))
    metric_cols[2].metric("评测运行", len(runs))
    metric_cols[3].metric("反馈记录", len(feedback_items))


def _eval_case_label(cases: list[dict], value: str) -> str:
    if value == "__new__":
        return "新建用例"
    return next((case.get("name", value) for case in cases if case.get("case_id") == value), value)


def _render_eval_case_selector(cases: list[dict]) -> tuple[str, dict]:
    edit_options = ["__new__"] + [str(case.get("case_id") or "") for case in cases]
    edit_case_id = st.selectbox(
        "编辑目标",
        options=edit_options,
        format_func=lambda value: _eval_case_label(cases, value),
        key="rag_eval_edit_case_id",
    )
    current_case = next((case for case in cases if case.get("case_id") == edit_case_id), {}) if edit_case_id != "__new__" else {}
    return edit_case_id, current_case


def _render_eval_case_filters(current_case: dict, edit_case_id: str, source_type_candidates: list[str]) -> dict:
    eval_col_a, eval_col_b, eval_col_c = st.columns(3)
    expected_source_types = eval_col_a.multiselect(
        "期望来源类型（可选）",
        options=source_type_candidates,
        default=[item for item in current_case.get("expected_source_types", []) if item in source_type_candidates],
        format_func=label_source_type,
        key=f"rag_eval_expected_source_types_{edit_case_id}",
    )
    profile_options = [""] + list(RETRIEVAL_TASK_PROFILES.keys())
    eval_profile = eval_col_b.selectbox(
        "任务策略",
        options=profile_options,
        index=profile_options.index(current_case.get("retrieval_profile", "")) if current_case.get("retrieval_profile", "") in profile_options else 0,
        format_func=retrieval_profile_label,
        key=f"rag_eval_profile_{edit_case_id}",
    )
    eval_mode = eval_col_c.selectbox(
        "检索模式",
        options=["hybrid", "lexical", "semantic"],
        index=["hybrid", "lexical", "semantic"].index(current_case.get("retrieval_mode", "hybrid")) if current_case.get("retrieval_mode", "hybrid") in {"hybrid", "lexical", "semantic"} else 0,
        format_func=label_retrieval_mode,
        key=f"rag_eval_mode_{edit_case_id}",
    )
    scope_values = st.multiselect(
        "范围过滤",
        options=["project", "canon", "reference"],
        default=current_case.get("allowed_scopes", []) or ["project", "canon", "reference"],
        format_func=label_scope,
        key=f"rag_eval_scopes_{edit_case_id}",
    )
    source_type_values = st.multiselect(
        "来源类型过滤（可选）",
        options=source_type_candidates,
        default=[item for item in current_case.get("allowed_source_types", []) if item in source_type_candidates],
        format_func=label_source_type,
        key=f"rag_eval_allowed_source_types_{edit_case_id}",
    )
    return {
        "expected_source_types": expected_source_types,
        "allowed_scopes": scope_values,
        "allowed_source_types": source_type_values,
        "retrieval_profile": eval_profile,
        "retrieval_mode": eval_mode,
    }


def _render_eval_case_config(current_case: dict, edit_case_id: str) -> dict:
    config_col_a, config_col_b, config_col_c = st.columns(3)
    eval_top_k = config_col_a.number_input(
        "返回条数",
        min_value=1,
        max_value=20,
        value=int(current_case.get("top_k", 6) or 6),
        key=f"rag_eval_top_k_{edit_case_id}",
    )
    eval_min_matches = config_col_b.number_input(
        "最少命中预期数",
        min_value=1,
        max_value=20,
        value=int(current_case.get("min_expected_matches", 1) or 1),
        key=f"rag_eval_min_matches_{edit_case_id}",
    )
    eval_status = config_col_c.selectbox(
        "状态",
        options=["active", "disabled"],
        index=0 if current_case.get("status", "active") != "disabled" else 1,
        format_func=lambda value: "启用" if value == "active" else "停用",
        key=f"rag_eval_status_{edit_case_id}",
    )
    return {"top_k": int(eval_top_k), "min_expected_matches": int(eval_min_matches), "status": eval_status}


def _render_eval_case_form_payload(current_case: dict, edit_case_id: str, source_type_candidates: list[str]) -> dict:
    case_name = st.text_input("用例名称", value=current_case.get("name", ""), key=f"rag_eval_case_name_{edit_case_id}")
    case_query = st.text_area("测试查询", value=current_case.get("query", ""), height=90, key=f"rag_eval_case_query_{edit_case_id}")
    expected_terms_text = st.text_area(
        "期望命中词（逗号或换行分隔）",
        value="\n".join(current_case.get("expected_terms", [])),
        height=80,
        key=f"rag_eval_expected_terms_{edit_case_id}",
    )
    expected_chunk_ids_text = st.text_area(
        "期望片段 ID（可选，逗号或换行分隔）",
        value="\n".join(current_case.get("expected_chunk_ids", [])),
        height=70,
        key=f"rag_eval_expected_chunks_{edit_case_id}",
    )
    payload = {
        "case_id": "" if edit_case_id == "__new__" else edit_case_id,
        "name": case_name,
        "query": case_query,
        "expected_terms": parse_multiline_or_comma_values(expected_terms_text),
        "expected_chunk_ids": parse_multiline_or_comma_values(expected_chunk_ids_text),
    }
    payload.update(_render_eval_case_filters(current_case, edit_case_id, source_type_candidates))
    payload.update(_render_eval_case_config(current_case, edit_case_id))
    payload["notes"] = st.text_area("备注", value=current_case.get("notes", ""), height=70, key=f"rag_eval_notes_{edit_case_id}")
    return payload


def _render_eval_case_editor(project_name: str, cases: list[dict], source_type_candidates: list[str]) -> None:
    with st.expander("新增 / 更新评测用例", expanded=False):
        edit_case_id, current_case = _render_eval_case_selector(cases)
        payload = _render_eval_case_form_payload(current_case, edit_case_id, source_type_candidates)
        if st.button("保存评测用例", key=f"save_rag_eval_case_{edit_case_id}", use_container_width=True):
            try:
                saved = upsert_retrieval_eval_case(project_name, payload)
                st.success(f"已保存评测用例：{saved.get('name')}")
                st.rerun()
            except Exception as exc:
                st.error(f"保存失败：{exc}")


def _render_eval_cases_table(cases: list[dict]) -> None:
    rows = [
        {
            "名称": case.get("name", ""),
            "查询": case.get("query", "")[:80],
            "期望词": "、".join(case.get("expected_terms", [])[:5]),
            "期望来源": "、".join(label_source_type(item) for item in case.get("expected_source_types", [])[:5]),
            "策略": retrieval_profile_label(case.get("retrieval_profile", "")),
            "状态": "启用" if case.get("status", "active") == "active" else "停用",
        }
        for case in cases
    ]
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_eval_case_actions(project_name: str, cases: list[dict]) -> None:
    action_col_a, action_col_b, action_col_c = st.columns(3)
    selected_case_id = action_col_a.selectbox(
        "选择运行/删除用例",
        options=[str(case.get("case_id") or "") for case in cases],
        format_func=lambda value: _eval_case_label(cases, value),
        key="rag_eval_selected_case",
    )
    if action_col_b.button("运行所选用例", key="run_selected_rag_eval", use_container_width=True):
        selected_case = next((case for case in cases if case.get("case_id") == selected_case_id), None)
        if selected_case:
            run = run_retrieval_eval_cases(project_name, [selected_case], note="手动运行单个评测用例")
            st.session_state["rag_eval_last_run"] = run
            st.success(f"评测完成：通过 {run.get('passed_count', 0)} / {run.get('case_count', 0)}")
    if confirmed_button(
        action_col_c,
        "删除所选用例",
        "确认删除所选用例",
        scoped_widget_key("delete_selected_rag_eval", project_name),
    ):
        if delete_retrieval_eval_case(project_name, selected_case_id):
            st.success("已删除评测用例。")
            st.rerun()
    if st.button("运行全部启用评测用例", key="run_all_rag_eval", use_container_width=True):
        run = run_retrieval_eval_cases(project_name, cases, note="手动运行全部启用评测用例")
        st.session_state["rag_eval_last_run"] = run
        st.success(f"评测完成：通过 {run.get('passed_count', 0)} / {run.get('case_count', 0)}，通过率 {run.get('pass_rate', 0):.0%}")


def _render_eval_cases(project_name: str, cases: list[dict]) -> None:
    if not cases:
        return
    _render_eval_cases_table(cases)
    _render_eval_case_actions(project_name, cases)


def _eval_result_rows(last_run: dict) -> list[dict]:
    rows = []
    for result in last_run.get("results", []):
        top_hit = result.get("top_hit", {}).get("chunk", {}) if isinstance(result.get("top_hit", {}), dict) else {}
        rows.append({
            "结果": "通过" if result.get("passed") else "未通过",
            "用例": result.get("name", ""),
            "命中": f"{result.get('matched_count', 0)} / {result.get('expectation_count', 0)}",
            "Top1": f"{label_source_type(top_hit.get('source_type', ''))} / {top_hit.get('title', '')}" if top_hit else "-",
            "错误": result.get("error", ""),
        })
    return rows


def _render_last_eval_run(runs: list[dict]) -> None:
    last_run = st.session_state.get("rag_eval_last_run") or (runs[0] if runs else {})
    if not last_run:
        return
    with st.expander("最近一次评测结果", expanded=True):
        st.caption(
            f"处理记录 ID={last_run.get('run_id', '')} / 通过 {last_run.get('passed_count', 0)} / "
            f"总数 {last_run.get('case_count', 0)} / 通过率 {last_run.get('pass_rate', 0):.0%}"
        )
        result_rows = _eval_result_rows(last_run)
        if result_rows:
            st.dataframe(result_rows, use_container_width=True, hide_index=True)
        render_step_json_expander("评测运行原始数据", last_run)


def _render_retrieval_feedback(feedback_items: list[dict]) -> None:
    if not feedback_items:
        return
    with st.expander("最近检索反馈", expanded=False):
        st.dataframe(
            [
                {
                    "时间": item.get("created_at", "")[:19],
                    "反馈": item.get("rating", ""),
                    "查询": item.get("query", "")[:50],
                    "来源": label_source_type(item.get("source_type", "")),
                    "标题": item.get("title", ""),
                    "备注": item.get("note", ""),
                }
                for item in reversed(feedback_items[-50:])
            ],
            use_container_width=True,
            hide_index=True,
        )


def render_retrieval_eval_workbench(project_name: str, manifest):
    cases, runs, feedback_items, source_type_candidates = _load_eval_workbench_state(project_name, manifest)
    with st.expander("RAG 评测与反馈", expanded=False):
        st.caption("用固定测试问题评估召回是否命中预期资料；检索反馈会影响后续排序，适合持续调教项目资料库。")
        _render_eval_metrics(cases, runs, feedback_items)
        _render_eval_case_editor(project_name, cases, source_type_candidates)
        _render_eval_cases(project_name, cases)
        _render_last_eval_run(runs)
        _render_retrieval_feedback(feedback_items)

