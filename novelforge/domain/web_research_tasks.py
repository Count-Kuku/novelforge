"""Pure state transitions for durable web-research tasks."""

from __future__ import annotations

from datetime import datetime, timezone
import math
from uuid import uuid4

from novelforge.domain.llm_preflight import build_preflight_estimate, build_stage_estimate


WEB_RESEARCH_WORKFLOW_TYPE = "web_research"
WEB_RESEARCH_STAGE_NAMES = ("plan", "search", "fetch", "extract", "verify", "evaluate")
WEB_RESEARCH_STAGE_STATUSES = {"pending", "running", "completed", "failed", "skipped"}
WEB_RESEARCH_TASK_STATUSES = {
    "queued",
    "running",
    "paused",
    "failed",
    "completed_with_errors",
    "completed",
    "cancelled",
}
WEB_RESEARCH_TERMINAL_STATUSES = {"completed", "cancelled"}

_RESULT_INVALIDATION_BY_STAGE = {
    "plan": {
        "plan", "branch_results", "search_hits", "search_errors", "selected_hits",
        "fetched_sources", "fetch_errors", "claims", "page_extractions",
        "extraction_errors", "verification", "verified_claims", "evaluation",
    },
    "search": {
        "branch_results", "search_hits", "search_errors", "selected_hits",
        "fetched_sources", "fetch_errors", "claims", "page_extractions",
        "extraction_errors", "verification", "verified_claims", "evaluation",
    },
    "fetch": {
        "fetch_errors", "claims", "page_extractions", "extraction_errors",
        "verification", "verified_claims", "evaluation",
    },
    "extract": {
        "claims", "page_extractions", "extraction_errors", "verification",
        "verified_claims", "evaluation",
    },
    "verify": {"verification", "verified_claims", "evaluation"},
    "evaluate": {"evaluation"},
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_snapshot(raw: dict | None, name: str, order: int) -> dict:
    source = dict(raw or {})
    status = str(source.get("status") or "pending")
    if status not in WEB_RESEARCH_STAGE_STATUSES:
        status = "pending"
    return {
        **source,
        "step_name": name,
        "step_order": order,
        "status": status,
        "input": dict(source.get("input") or {}),
        "output": dict(source.get("output") or {}),
        "error": str(source.get("error") or ""),
        "attempt_count": max(0, int(source.get("attempt_count") or 0)),
        "started_at": str(source.get("started_at") or ""),
        "finished_at": str(source.get("finished_at") or ""),
        "updated_at": str(source.get("updated_at") or ""),
    }


def normalize_web_research_task(task: dict | None) -> dict:
    raw = dict(task or {})
    now = _now_iso()
    task_id = str(raw.get("task_id") or raw.get("run_id") or f"web_research_{uuid4().hex}")
    status = str(raw.get("status") or "queued")
    if status not in WEB_RESEARCH_TASK_STATUSES:
        status = "queued"
    raw_steps = raw.get("steps", {}) if isinstance(raw.get("steps"), dict) else {}
    steps = {
        name: _stage_snapshot(raw_steps.get(name), name, order)
        for order, name in enumerate(WEB_RESEARCH_STAGE_NAMES, start=1)
    }
    completed = sum(1 for step in steps.values() if step["status"] in {"completed", "skipped"})
    failed = sum(1 for step in steps.values() if step["status"] == "failed")
    return {
        **raw,
        "task_id": task_id,
        "run_id": task_id,
        "workflow_type": WEB_RESEARCH_WORKFLOW_TYPE,
        "story_id": str(raw.get("story_id") or ""),
        "title": str(raw.get("title") or "网络资料研究"),
        "topic": str(raw.get("topic") or "").strip(),
        "objective": str(raw.get("objective") or "").strip(),
        "status": status,
        "configuration": dict(raw.get("configuration") or {}),
        "estimate": dict(raw.get("estimate") or {}),
        "priority": int(raw.get("priority") or 0),
        "steps": steps,
        "result": dict(raw.get("result") or {}),
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
        "started_at": str(raw.get("started_at") or ""),
        "finished_at": str(raw.get("finished_at") or ""),
        "paused_at": str(raw.get("paused_at") or ""),
        "cancelled_at": str(raw.get("cancelled_at") or ""),
        "current_message": str(raw.get("current_message") or ""),
        "last_error": str(raw.get("last_error") or ""),
        "worker_id": str(raw.get("worker_id") or ""),
        "lease_expires_at": str(raw.get("lease_expires_at") or ""),
        "heartbeat_at": str(raw.get("heartbeat_at") or ""),
        "control_requested": str(raw.get("control_requested") or ""),
        "archived_at": str(raw.get("archived_at") or ""),
        "progress": {
            "total": len(steps),
            "completed": completed,
            "failed": failed,
            "percent": completed / len(steps) if steps else 0.0,
        },
    }


def build_web_research_estimate(
    configuration: dict,
    *,
    model_profile: dict | None = None,
    calibrations: dict | None = None,
) -> dict:
    max_pages = max(1, min(int(configuration.get("max_pages") or 8), 50))
    branch_count = max(1, len(configuration.get("source_kinds") or ["general"]))
    planner_calls = 1 if configuration.get("use_llm_planner", True) else 0
    extraction_calls = max_pages
    verifier_calls = 1 if configuration.get("use_llm_verifier", True) else 0
    max_chars_per_page = max(
        2000, min(int(configuration.get("max_chars_per_page") or 30000), 60000)
    )
    max_claims_per_page = max(
        1, min(int(configuration.get("max_claims_per_page") or 20), 100)
    )
    category_count = max(len(configuration.get("enabled_categories") or []), 1)
    history = dict(calibrations or {})
    stages: list[dict] = []
    if planner_calls:
        stages.append(
            build_stage_estimate(
                "研究规划 Agent",
                operation="web_research.plan",
                agent_role="planner",
                call_count=planner_calls,
                input_tokens_per_call={"low": 700, "expected": 1200, "high": 2000},
                output_tokens_per_call={"low": 350, "expected": 800, "high": 1400},
                calibration=history.get("plan"),
                calibrate_input=True,
                calibrate_output=True,
                confidence="medium",
            )
        )

    extraction_input = max(1500, math.ceil(max_chars_per_page * 0.25) + 1000)
    extraction_output = max(
        900,
        min(3200, 500 + max_claims_per_page * 55 + category_count * 35),
    )
    stages.append(
        build_stage_estimate(
            "网页事实提取 Agent",
            operation="web_research.extract",
            agent_role="extractor",
            call_count=extraction_calls,
            input_tokens_per_call={
                "low": max(900, math.ceil(extraction_input * 0.35)),
                "expected": extraction_input,
                "high": math.ceil(max_chars_per_page / 1.6) + 1500,
            },
            output_tokens_per_call={
                "low": math.ceil(extraction_output * 0.45),
                "expected": extraction_output,
                "high": math.ceil(extraction_output * 1.6),
            },
            calibration=history.get("extract"),
            calibrate_input=True,
            calibrate_output=True,
            confidence="low",
            assumptions=["网页实际正文长度和抓取成功数未知，提取阶段区间较宽。"],
        )
    )
    if verifier_calls:
        verifier_input = max(
            2500,
            min(24000, max_pages * max_claims_per_page * 30 + 1000),
        )
        verifier_output = max(1000, min(5000, max_pages * max_claims_per_page * 12 + 600))
        stages.append(
            build_stage_estimate(
                "冲突验证 Agent",
                operation="web_research.verify",
                agent_role="verifier",
                call_count=verifier_calls,
                input_tokens_per_call={
                    "low": math.ceil(verifier_input * 0.4),
                    "expected": verifier_input,
                    "high": math.ceil(verifier_input * 1.45),
                },
                output_tokens_per_call={
                    "low": math.ceil(verifier_output * 0.45),
                    "expected": verifier_output,
                    "high": math.ceil(verifier_output * 1.6),
                },
                calibration=history.get("verify"),
                calibrate_input=True,
                calibrate_output=True,
                confidence="low",
            )
        )

    result = build_preflight_estimate(
        stages,
        profile=model_profile,
        estimate_kind="web_research",
        external_calls=[
            {
                "kind": "search",
                "label": "搜索 API",
                "count": branch_count,
                "cost_included": False,
            },
            {
                "kind": "fetch",
                "label": "公开网页抓取",
                "count": max_pages,
                "cost_included": False,
            },
        ],
        assumptions=[
            "模型费用不包含 Brave Search、代理或其它外部工具可能产生的独立费用。",
            "未成功抓取的网页不会进入事实提取，实际模型调用可能低于上界。",
            "抓取原文先进入隔离区，本任务不生成向量；人工激活时的向量费用不计入本次预估。",
        ],
    )
    result.update(
        {
            "estimated_search_calls": branch_count,
            "estimated_fetch_calls": max_pages,
            "estimated_cost_usd": float(result.get("estimated_cost_usd") or 0.0),
        }
    )
    return result


def create_web_research_task(
    topic: str,
    *,
    objective: str = "",
    story_id: str = "",
    configuration: dict | None = None,
    priority: int = 0,
    estimate: dict | None = None,
) -> dict:
    cleaned_topic = " ".join(str(topic or "").split())
    if not cleaned_topic:
        raise ValueError("网络研究主题不能为空。")
    if len(cleaned_topic) > 200:
        raise ValueError("网络研究主题不能超过 200 个字符。")
    cleaned_objective = str(objective or "").strip()
    if len(cleaned_objective) > 2000:
        raise ValueError("网络研究目标不能超过 2000 个字符。")
    now = _now_iso()
    task_id = f"web_research_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid4().hex[:8]}"
    normalized_configuration = dict(configuration or {})
    return normalize_web_research_task(
        {
            "task_id": task_id,
            "story_id": story_id,
            "title": f"研究：{cleaned_topic}",
            "topic": cleaned_topic,
            "objective": cleaned_objective,
            "status": "queued",
            "configuration": normalized_configuration,
            "estimate": dict(estimate or build_web_research_estimate(normalized_configuration)),
            "priority": int(priority),
            "steps": {},
            "result": {},
            "created_at": now,
            "updated_at": now,
            "current_message": "等待后台研究 worker。",
        }
    )


def set_web_research_task_status(task: dict, status: str, *, message: str = "", error: str = "") -> dict:
    if status not in WEB_RESEARCH_TASK_STATUSES:
        raise ValueError(f"不支持的网络研究任务状态：{status}")
    normalized = normalize_web_research_task(task)
    now = _now_iso()
    normalized["status"] = status
    normalized["updated_at"] = now
    if message:
        normalized["current_message"] = message
    if error:
        normalized["last_error"] = error
    if status == "running":
        normalized["started_at"] = normalized.get("started_at") or now
        normalized["finished_at"] = ""
        normalized["paused_at"] = ""
    elif status == "paused":
        normalized["paused_at"] = now
        for step in normalized["steps"].values():
            if step["status"] == "running":
                step["status"] = "pending"
                step["updated_at"] = now
    elif status == "cancelled":
        normalized["cancelled_at"] = now
        normalized["finished_at"] = now
    elif status in {"completed", "completed_with_errors"}:
        normalized["finished_at"] = now
    return normalize_web_research_task(normalized)


def update_web_research_stage(
    task: dict,
    stage_name: str,
    status: str,
    *,
    output: dict | None = None,
    error: str = "",
) -> dict:
    if stage_name not in WEB_RESEARCH_STAGE_NAMES or status not in WEB_RESEARCH_STAGE_STATUSES:
        raise ValueError("网络研究阶段或状态无效。")
    normalized = normalize_web_research_task(task)
    step = normalized["steps"][stage_name]
    now = _now_iso()
    if status == "running" and step["status"] != "running":
        step["attempt_count"] += 1
        step["started_at"] = now
        step["finished_at"] = ""
    if status in {"completed", "failed", "skipped"}:
        step["finished_at"] = now
    step["status"] = status
    step["error"] = str(error or "")
    if output is not None:
        step["output"] = dict(output)
    step["updated_at"] = now
    normalized["updated_at"] = now
    return normalize_web_research_task(normalized)


def retry_failed_web_research_task(task: dict) -> dict:
    normalized = normalize_web_research_task(task)
    failed_indices = [
        index for index, name in enumerate(WEB_RESEARCH_STAGE_NAMES)
        if normalized["steps"][name]["status"] == "failed"
    ]
    if not failed_indices and normalized.get("status") == "completed_with_errors":
        failed_indices = [
            index for index, name in enumerate(WEB_RESEARCH_STAGE_NAMES)
            if isinstance(normalized["steps"][name].get("output"), dict)
            and normalized["steps"][name]["output"].get("errors")
        ]
    if not failed_indices:
        raise ValueError("当前网络研究任务没有失败或部分失败阶段可重试。")
    first_failed = min(failed_indices)
    now = _now_iso()
    for name in WEB_RESEARCH_STAGE_NAMES[first_failed:]:
        step = normalized["steps"][name]
        step["status"] = "pending"
        step["error"] = ""
        step["output"] = {}
        step["finished_at"] = ""
        step["updated_at"] = now
    retry_stage = WEB_RESEARCH_STAGE_NAMES[first_failed]
    result = dict(normalized.get("result") or {})
    preserved_queue_ids = list(result.get("queued_pending_ids") or [])
    for key in _RESULT_INVALIDATION_BY_STAGE[retry_stage]:
        result.pop(key, None)
    if preserved_queue_ids:
        result["queued_pending_ids"] = preserved_queue_ids
    if retry_stage in {"plan", "search", "fetch"}:
        result["raw_sources_retrieval_status"] = "quarantine"
    normalized["result"] = result
    normalized["retry_from_stage"] = retry_stage
    normalized["status"] = "queued"
    normalized["finished_at"] = ""
    normalized["last_error"] = ""
    normalized["current_message"] = f"将从“{retry_stage}”阶段继续。"
    normalized["updated_at"] = now
    return normalize_web_research_task(normalized)
