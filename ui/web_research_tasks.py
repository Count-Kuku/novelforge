"""Durable multi-role web-research task UI."""

from __future__ import annotations

import os

import streamlit as st

from novelforge.services.memory import list_web_research_tasks, load_web_research_task
from novelforge.services.web_research import load_imported_web_page
from novelforge.workflows.web_research_task_dispatcher import (
    get_web_research_task_dispatcher_status,
    wake_web_research_task_dispatcher,
)
from novelforge.workflows.web_research_tasks import (
    build_web_research_task_estimate,
    activate_web_research_sources,
    archive_web_research_task,
    cancel_web_research_task,
    create_web_research_task,
    delete_web_research_task,
    pause_web_research_task,
    quarantine_web_research_sources,
    queue_web_research_claims_for_review,
    restore_web_research_task,
    resume_web_research_task,
    retry_web_research_task,
)
from ui.common import scoped_session_key, scoped_widget_key
from ui.labels import KNOWLEDGE_CATEGORY_LABELS, label_scope
from ui.llm_preflight import render_preflight_estimate


SOURCE_KIND_LABELS = {
    "official": "官方来源",
    "secondary": "百科与整理",
    "community": "社区考据",
    "fanon": "同人私设",
    "general": "综合资料",
}
TASK_STATUS_LABELS = {
    "queued": "等待中",
    "running": "研究中",
    "paused": "已暂停",
    "failed": "失败",
    "completed_with_errors": "部分完成",
    "completed": "已完成",
    "cancelled": "已取消",
}
STAGE_LABELS = {
    "plan": "研究规划",
    "search": "并行搜索",
    "fetch": "安全抓取",
    "extract": "事实提取",
    "verify": "交叉验证",
    "evaluate": "质量评测",
}
VERIFICATION_LABELS = {
    "supported": "多来源支持",
    "single_source": "单一来源",
    "contested": "存在冲突",
    "rejected": "证据不足",
}


def _selected_task_key(project_name: str, story_id: str) -> str:
    return scoped_session_key("web_research_selected_task", project_name, story_id)


def _render_task_creator(project_name: str, story_id: str) -> None:
    st.markdown("##### 创建自动研究任务")
    st.caption(
        "Planner 会拆分查询，多个 Collector 并行搜索；抓取、事实提取和验证结果会分阶段保存。"
        "任务只生成审核候选，不会直接写入正式知识。"
    )
    if not os.getenv("BRAVE_SEARCH_API_KEY", "").strip():
        st.warning("尚未配置 BRAVE_SEARCH_API_KEY；任务会保存，但搜索阶段会失败并可在配置后重试。")

    with st.form(scoped_widget_key("web_research_task_form", project_name, story_id)):
        topic = st.text_input(
            "研究主题",
            placeholder="例如：原神 坎瑞亚 历史、人物和官方时间线",
        )
        objective = st.text_area(
            "研究目标",
            placeholder="例如：区分官方设定、社区考据和同人私设，并标出相互冲突的说法。",
            height=80,
        )
        source_kinds = st.multiselect(
            "来源角色",
            options=list(SOURCE_KIND_LABELS),
            default=["official", "secondary", "community", "fanon"],
            format_func=lambda value: SOURCE_KIND_LABELS[value],
        )
        official_domains_text = st.text_input(
            "已知官方域名（可选，逗号分隔）",
            placeholder="例如：hoyoverse.com, hoyolab.com",
            help="只有匹配这里的域名才会被自动评为“官方”；仅仅出现在官方搜索分支中并不够。",
        )
        option_cols = st.columns(4)
        max_results = option_cols[0].slider("每分支结果", 2, 10, 5)
        max_pages = option_cols[1].slider("最多抓取页", 2, 12, 6)
        language = option_cols[2].selectbox(
            "结果语言",
            ["zh-hans", "en"],
            format_func=lambda value: "简体中文" if value == "zh-hans" else "英文",
        )
        freshness = option_cols[3].selectbox(
            "时间范围",
            ["", "pw", "pm", "py"],
            format_func=lambda value: {"": "不限", "pw": "一周", "pm": "一月", "py": "一年"}[value],
        )
        categories = st.multiselect(
            "提取内容",
            options=list(KNOWLEDGE_CATEGORY_LABELS),
            default=[
                "characters",
                "world_rules",
                "locations",
                "organizations",
                "timeline_events",
                "relationships",
                "constraints",
            ],
            format_func=lambda value: KNOWLEDGE_CATEGORY_LABELS[value],
        )
        behavior_cols = st.columns(3)
        scope = behavior_cols[0].selectbox(
            "资料范围",
            ["reference", "canon"],
            format_func=label_scope,
        )
        use_llm_planner = behavior_cols[1].checkbox("模型规划查询", value=True)
        use_llm_verifier = behavior_cols[2].checkbox("模型识别语义冲突", value=True)
        estimate = build_web_research_task_estimate(
            {
                "max_pages": max_pages,
                "source_kinds": source_kinds,
                "use_llm_planner": use_llm_planner,
                "use_llm_verifier": use_llm_verifier,
                "enabled_categories": categories,
                "max_chars_per_page": 30000,
                "max_claims_per_page": 20,
            }
        )
        estimate_approved = render_preflight_estimate(
            estimate,
            expanded=max_pages >= 8,
            confirmation_key=scoped_widget_key(
                "web_research_budget_confirm", project_name, story_id
            ),
        )
        submitted = st.form_submit_button("创建后台研究任务", type="primary", width="stretch")

    if not submitted:
        return
    if not topic.strip():
        st.error("请填写研究主题。")
        return
    if not source_kinds or not categories:
        st.error("至少选择一个来源角色和一个提取分类。")
        return
    if not estimate_approved:
        st.error("本次预估超过预算确认阈值，请先确认 Token 与费用上界。")
        return
    official_domains = [
        item.strip()
        for item in official_domains_text.replace("，", ",").split(",")
        if item.strip()
    ]
    try:
        task = create_web_research_task(
            project_name,
            topic,
            objective=objective,
            source_kinds=source_kinds,
            official_domains=official_domains,
            max_results_per_branch=max_results,
            max_pages=max_pages,
            enabled_categories=categories,
            language=language,
            freshness=freshness,
            scope=scope,
            use_llm_planner=use_llm_planner,
            use_llm_verifier=use_llm_verifier,
            story_id=story_id,
        )
        st.session_state[_selected_task_key(project_name, story_id)] = task["task_id"]
        wake_web_research_task_dispatcher()
        st.success("网络研究任务已创建并放入后台队列。")
        st.rerun()
    except Exception as exc:
        st.error(f"创建网络研究任务失败：{exc}")


def _run_action(label: str, key: str, action, *, wake: bool = False) -> None:
    if not st.button(label, key=key, width="stretch"):
        return
    try:
        action()
        if wake:
            wake_web_research_task_dispatcher()
        st.rerun()
    except Exception as exc:
        st.error(f"操作失败：{exc}")


def _render_stage_progress(task: dict) -> None:
    progress = task.get("progress", {})
    st.progress(float(progress.get("percent") or 0.0), text=str(task.get("current_message") or ""))
    rows = []
    for name, step in task.get("steps", {}).items():
        rows.append(
            {
                "阶段": STAGE_LABELS.get(name, name),
                "状态": step.get("status", "pending"),
                "尝试次数": step.get("attempt_count", 0),
                "错误": step.get("error", ""),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def _render_evaluation(task: dict) -> None:
    evaluation = task.get("result", {}).get("evaluation", {})
    if not evaluation:
        return
    st.markdown("##### 研究质量")
    cols = st.columns(5)
    cols[0].metric("查询覆盖", f"{float(evaluation.get('branch_coverage') or 0):.0%}")
    cols[1].metric("来源角色覆盖", f"{float(evaluation.get('source_kind_coverage') or 0):.0%}")
    cols[2].metric("抓取成功", f"{float(evaluation.get('fetch_success_rate') or 0):.0%}")
    cols[3].metric("多来源支持", f"{float(evaluation.get('corroboration_rate') or 0):.0%}")
    cols[4].metric("冲突率", f"{float(evaluation.get('conflict_rate') or 0):.0%}")
    st.caption(
        f"唯一网页 {evaluation.get('unique_hit_count', 0)} 个 / 域名 {evaluation.get('unique_domain_count', 0)} 个 / "
        f"搜索结果重复率 {float(evaluation.get('duplicate_rate') or 0):.0%} / "
        f"有效候选 {int(evaluation.get('candidate_claim_count') or 0) - int(evaluation.get('rejected_claim_count') or 0)}"
        f"/{int(evaluation.get('candidate_claim_count') or 0)} / "
        f"可定位引文率 {float(evaluation.get('evidence_valid_rate') or 0):.0%}"
    )


def _render_claim_review(project_name: str, story_id: str, task: dict) -> None:
    claims = task.get("result", {}).get("verified_claims", [])
    if not claims:
        st.info("任务没有生成可审核的事实主张。")
        return
    selected_ids: list[str] = []
    st.markdown("##### 研究结论与证据")
    st.caption("选择后只会进入“待审核设定”；仍需人工确认，存在冲突的候选默认不选。")
    for index, claim in enumerate(claims, start=1):
        claim_id = str(claim.get("claim_id") or "")
        status = str(claim.get("verification_status") or "single_source")
        with st.container(border=True):
            choose_col, text_col = st.columns([1, 11])
            chosen = choose_col.checkbox(
                "选择",
                value=status in {"supported", "single_source"} and float(claim.get("confidence") or 0) >= 0.4,
                label_visibility="collapsed",
                key=scoped_widget_key("web_claim_select", project_name, story_id, task["task_id"], claim_id),
            )
            category = KNOWLEDGE_CATEGORY_LABELS.get(str(claim.get("category") or ""), claim.get("category", ""))
            text_col.markdown(f"**{index}. {claim.get('name') or '未命名'}** · {category} · {VERIFICATION_LABELS.get(status, status)}")
            text_col.write(str(claim.get("summary") or ""))
            text_col.caption(
                f"可信度 {float(claim.get('confidence') or 0):.2f} · 证据强度 {float(claim.get('evidence_strength') or 0):.2f} · "
                f"来源可信度 {claim.get('authority', 'unknown')}"
            )
            if claim.get("verification_rationale"):
                text_col.caption(str(claim["verification_rationale"]))
            with text_col.expander(f"查看证据（{len(claim.get('evidence') or [])}）", expanded=status == "contested"):
                for evidence in claim.get("evidence", []):
                    stance = "反对/冲突证据" if evidence.get("stance") == "contradict" else "支持证据"
                    st.markdown(f"- **[{stance}] {evidence.get('source_title') or evidence.get('source_url')}**")
                    st.caption(str(evidence.get("source_url") or ""))
                    st.write(f"“{evidence.get('quote') or ''}”")
            if chosen:
                selected_ids.append(claim_id)
    if st.button(
        f"将选中的 {len(selected_ids)} 条送入待审核设定",
        disabled=not selected_ids,
        type="primary",
        width="stretch",
        key=scoped_widget_key("queue_web_claims", project_name, story_id, task["task_id"]),
    ):
        try:
            result = queue_web_research_claims_for_review(project_name, task["task_id"], selected_ids)
            st.success(f"已提交 {len(result.get('pending_ids', []))} 条候选；重复提交会更新同一条记录。")
            st.rerun()
        except Exception as exc:
            st.error(f"提交待审核设定失败：{exc}")


def _render_task_detail(project_name: str, story_id: str, task: dict) -> None:
    status = str(task.get("status") or "")
    st.markdown(f"#### {task.get('title') or task.get('topic')} · {TASK_STATUS_LABELS.get(status, status)}")
    st.caption(f"任务 ID：{task.get('task_id')} · 更新时间：{task.get('updated_at', '')}")
    dispatcher = get_web_research_task_dispatcher_status()
    if dispatcher.get("running"):
        st.caption("网络研究后台 worker 正在运行。")
    _render_stage_progress(task)
    if task.get("last_error"):
        st.error(str(task["last_error"]))

    action_cols = st.columns(4)
    archived = bool(task.get("archived_at"))
    if status == "running" and not archived:
        with action_cols[0]:
            _run_action("暂停", f"pause_{task['task_id']}", lambda: pause_web_research_task(project_name, task["task_id"]))
        with action_cols[1]:
            _run_action("取消", f"cancel_{task['task_id']}", lambda: cancel_web_research_task(project_name, task["task_id"]))
    elif status == "queued" and not archived:
        with action_cols[0]:
            _run_action("取消", f"cancel_{task['task_id']}", lambda: cancel_web_research_task(project_name, task["task_id"]))
    elif status == "paused" and not archived:
        with action_cols[0]:
            _run_action("继续", f"resume_{task['task_id']}", lambda: resume_web_research_task(project_name, task["task_id"]), wake=True)
    elif status in {"failed", "completed_with_errors"} and not archived:
        with action_cols[0]:
            _run_action("重试失败阶段", f"retry_{task['task_id']}", lambda: retry_web_research_task(project_name, task["task_id"]), wake=True)
    if status in {"failed", "completed_with_errors", "completed", "cancelled", "paused"} and not archived:
        with action_cols[3]:
            _run_action("归档", f"archive_{task['task_id']}", lambda: archive_web_research_task(project_name, task["task_id"]))
    elif archived:
        with action_cols[3]:
            _run_action("恢复归档", f"restore_{task['task_id']}", lambda: restore_web_research_task(project_name, task["task_id"]))
        with action_cols[2]:
            confirm_delete = st.checkbox(
                "确认永久删除",
                key=scoped_widget_key("confirm_delete_web_task", project_name, story_id, task["task_id"]),
            )
            if confirm_delete:
                _run_action("永久删除", f"delete_{task['task_id']}", lambda: delete_web_research_task(project_name, task["task_id"]))

    sources = task.get("result", {}).get("fetched_sources", [])
    if sources:
        with st.expander(f"已保存网页来源（{len(sources)}）", expanded=False):
            st.dataframe(sources, width="stretch", hide_index=True)
            preview_map = {
                str(item.get("relative_path") or ""): str(item.get("title") or item.get("url") or "网页")
                for item in sources
                if str(item.get("relative_path") or "")
            }
            if preview_map:
                preview_path = st.selectbox(
                    "预览抓取正文",
                    options=list(preview_map),
                    format_func=lambda value: preview_map[value],
                    key=scoped_widget_key("web_task_source_preview", project_name, story_id, task["task_id"]),
                )
                try:
                    page = load_imported_web_page(project_name, preview_path)
                    st.caption(page.final_url)
                    st.text_area(
                        "正文（只读预览）",
                        value=page.text[:6000],
                        height=260,
                        disabled=True,
                        key=scoped_widget_key(
                            "web_task_source_preview_text",
                            project_name,
                            story_id,
                            task["task_id"],
                            preview_path,
                        ),
                    )
                except Exception as exc:
                    st.warning(f"无法读取网页预览：{exc}")
        if status in {"completed", "completed_with_errors"} and not archived:
            retrieval_status = task.get("result", {}).get("raw_sources_retrieval_status", "quarantine")
            if retrieval_status == "active":
                st.success("这些网页原文已由你明确启用，可参与后续检索。")
                _run_action(
                    "重新隔离全部网页原文",
                    f"quarantine_sources_{task['task_id']}",
                    lambda: quarantine_web_research_sources(project_name, task["task_id"]),
                )
            else:
                st.warning("网页原文当前处于隔离状态，不会进入写作检索；已验证的事实仍可单独送入待审核设定。")
                _run_action(
                    "确认来源后，启用全部网页原文检索",
                    f"activate_sources_{task['task_id']}",
                    lambda: activate_web_research_sources(project_name, task["task_id"]),
                )
    _render_evaluation(task)
    if status in {"completed", "completed_with_errors"} and not archived:
        _render_claim_review(project_name, story_id, task)


def render_web_research_task_manager(project_name: str, story_id: str) -> None:
    _render_task_creator(project_name, story_id)
    st.divider()
    include_archived = st.checkbox(
        "显示已归档任务",
        key=scoped_widget_key("web_research_show_archived", project_name, story_id),
    )
    tasks = list_web_research_tasks(project_name, story_id, include_archived=include_archived)
    if not tasks:
        st.info("还没有网络研究任务。")
        return
    task_map = {str(task["task_id"]): task for task in tasks}
    state_key = _selected_task_key(project_name, story_id)
    selected_id = str(st.session_state.get(state_key) or "")
    if selected_id not in task_map:
        selected_id = next(iter(task_map))
    selected_id = st.selectbox(
        "研究任务",
        options=list(task_map),
        index=list(task_map).index(selected_id),
        format_func=lambda value: f"{TASK_STATUS_LABELS.get(task_map[value].get('status'), task_map[value].get('status'))} · {task_map[value].get('topic')}",
        key=scoped_widget_key("web_research_task_select", project_name, story_id),
    )
    st.session_state[state_key] = selected_id
    latest = load_web_research_task(project_name, selected_id) or task_map[selected_id]
    _render_task_detail(project_name, story_id, latest)
