"""Creation, control, recovery, and execution of durable web-research tasks."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

from novelforge.core.llm_usage import llm_usage_scope
from novelforge.core.schemas import WebResearchPlan, WebResearchVerificationResult
from novelforge.domain.web_research_tasks import (
    WEB_RESEARCH_STAGE_NAMES,
    create_web_research_task as create_task_state,
    normalize_web_research_task,
    retry_failed_web_research_task,
    set_web_research_task_status,
    update_web_research_stage,
)
from novelforge.services.memory import (
    claim_web_research_task,
    delete_archived_web_research_task,
    finalize_web_research_task,
    is_project_in_maintenance,
    load_web_research_task,
    load_web_research_task_control,
    queue_pending_knowledge_items,
    request_web_research_task_control,
    save_web_research_task,
    set_web_research_task_archived,
)
from novelforge.services.retrieval import rebuild_retrieval_assets
from novelforge.services.web_research import (
    delete_imported_web_pages,
    fetch_web_page,
    get_imported_web_pages_retrieval_statuses,
    import_fetched_web_pages,
    load_imported_web_page,
    set_imported_web_pages_retrieval_status,
)
from novelforge.workflows.web_research_agents import (
    assess_web_source,
    build_verified_research_claims,
    extract_claims_from_web_page,
    normalize_official_domains,
    plan_web_research_with_llm,
    select_research_hits,
    verify_research_claims,
)
from novelforge.workflows.web_research_evaluation import (
    evaluate_web_research_state,
    verified_claim_to_pending_item,
)
from novelforge.workflows.web_research_graph import (
    build_default_web_research_plan,
    build_web_research_graph,
)


DEFAULT_WEB_RESEARCH_LEASE_SECONDS = 45
DEFAULT_RESEARCH_CATEGORIES = [
    "characters",
    "items",
    "abilities",
    "world_rules",
    "locations",
    "organizations",
    "timeline_events",
    "relationships",
    "constraints",
]
ALL_RESEARCH_CATEGORIES = {
    *DEFAULT_RESEARCH_CATEGORIES,
    "writing_style",
    "dialogue_style",
    "narrative_techniques",
}


class WebResearchTaskLeaseUnavailable(RuntimeError):
    pass


class WebResearchTaskLeaseLost(RuntimeError):
    pass


class _WebResearchControlSignal(RuntimeError):
    def __init__(self, control: str):
        super().__init__(control)
        self.control = control


def create_web_research_task(
    project_name: str,
    topic: str,
    *,
    objective: str = "",
    source_kinds: list[str] | None = None,
    official_domains: list[str] | None = None,
    max_results_per_branch: int = 5,
    max_pages: int = 8,
    enabled_categories: list[str] | None = None,
    language: str = "zh-hans",
    freshness: str = "",
    scope: str = "reference",
    use_llm_planner: bool = True,
    use_llm_verifier: bool = True,
    max_chars_per_page: int = 30000,
    story_id: str = "",
    priority: int = 0,
) -> dict:
    if is_project_in_maintenance(project_name):
        raise ValueError("项目正在重命名或删除，暂时不能创建网络研究任务。")
    clean_kinds = [
        item for item in dict.fromkeys(str(value or "").lower() for value in (source_kinds or []))
        if item in {"official", "secondary", "community", "fanon", "general"}
    ] or ["official", "secondary", "community", "fanon"]
    clean_categories = [
        item
        for item in dict.fromkeys(str(value or "").strip() for value in (enabled_categories or DEFAULT_RESEARCH_CATEGORIES))
        if item in ALL_RESEARCH_CATEGORIES
    ]
    if not clean_categories:
        raise ValueError("至少选择一个受支持的网络资料提取分类。")
    clean_language = str(language or "zh-hans").strip().lower()
    if clean_language not in {"zh-hans", "en"}:
        raise ValueError("网络研究结果语言目前只支持 zh-hans 或 en。")
    clean_freshness = str(freshness or "").strip().lower()
    if clean_freshness not in {"", "pd", "pw", "pm", "py"}:
        raise ValueError("网络研究时间范围无效。")
    configuration = {
        "source_kinds": clean_kinds,
        "official_domains": normalize_official_domains(official_domains, strict=True),
        "max_results_per_branch": max(1, min(int(max_results_per_branch), 20)),
        "max_pages": max(1, min(int(max_pages), 20)),
        "enabled_categories": clean_categories,
        "language": clean_language,
        "freshness": clean_freshness,
        "scope": scope if scope in {"canon", "reference", "project"} else "reference",
        "use_llm_planner": bool(use_llm_planner),
        "use_llm_verifier": bool(use_llm_verifier),
        "max_chars_per_page": max(2000, min(int(max_chars_per_page), 60000)),
        "max_claims_per_page": 20,
        "max_concurrency": min(max(len(clean_kinds), 1), 5),
    }
    task = create_task_state(
        topic,
        objective=objective,
        story_id=story_id,
        configuration=configuration,
        priority=priority,
    )
    return save_web_research_task(project_name, task)


def _require_task(project_name: str, task_id: str) -> dict:
    task = load_web_research_task(project_name, task_id)
    if not task:
        raise FileNotFoundError(f"网络研究任务不存在：{task_id}")
    return task


def _require_not_archived(task: dict, action_label: str) -> None:
    if task.get("archived_at"):
        raise ValueError(f"归档的网络研究任务不能{action_label}；请先恢复归档。")


def pause_web_research_task(project_name: str, task_id: str) -> dict:
    task = _require_task(project_name, task_id)
    _require_not_archived(task, "暂停")
    result = request_web_research_task_control(project_name, task_id, "pause")
    task = _require_task(project_name, task_id)
    if result.get("immediate"):
        task = set_web_research_task_status(task, "paused", message="任务已暂停，可稍后继续。")
        return save_web_research_task(project_name, task)
    return task


def resume_web_research_task(project_name: str, task_id: str) -> dict:
    task = _require_task(project_name, task_id)
    _require_not_archived(task, "继续")
    request_web_research_task_control(project_name, task_id, "resume")
    task = _require_task(project_name, task_id)
    if task.get("status") == "running" or task.get("worker_id"):
        return task
    task = set_web_research_task_status(task, "queued", message="任务已放回网络研究队列。")
    task["finished_at"] = ""
    task["last_error"] = ""
    return save_web_research_task(project_name, task)


def cancel_web_research_task(project_name: str, task_id: str) -> dict:
    task = _require_task(project_name, task_id)
    _require_not_archived(task, "取消")
    result = request_web_research_task_control(project_name, task_id, "cancel")
    task = _require_task(project_name, task_id)
    if result.get("immediate"):
        task = set_web_research_task_status(task, "cancelled", message="网络研究任务已取消。")
        return save_web_research_task(project_name, task)
    return task


def retry_web_research_task(project_name: str, task_id: str) -> dict:
    if is_project_in_maintenance(project_name):
        raise ValueError("项目维护期间不能重试网络研究任务。")
    task = _require_task(project_name, task_id)
    _require_not_archived(task, "重试")
    if task.get("worker_id"):
        raise ValueError("任务仍由后台 worker 持有，不能重试。")
    existing_paths = list(dict.fromkeys([
        *[
            str(item)
            for item in task.get("result", {}).get("source_snapshot_paths", [])
            if str(item)
        ],
        *[
            str(item.get("relative_path") or "")
            for item in task.get("result", {}).get("fetched_sources", [])
            if str(item.get("relative_path") or "")
        ],
    ]))
    task = retry_failed_web_research_task(task)
    if task.get("retry_from_stage") in {"plan", "search", "fetch"} and existing_paths:
        set_imported_web_pages_retrieval_status(
            project_name,
            existing_paths,
            status="quarantine",
            build_vectors=True,
            research_task_id=task_id,
        )
    return save_web_research_task(project_name, task)


def archive_web_research_task(project_name: str, task_id: str) -> bool:
    return set_web_research_task_archived(project_name, task_id, True)


def restore_web_research_task(project_name: str, task_id: str) -> bool:
    return set_web_research_task_archived(project_name, task_id, False)


def delete_web_research_task(project_name: str, task_id: str) -> bool:
    task = _require_task(project_name, task_id)
    if not task.get("archived_at"):
        raise ValueError("网络研究任务必须先归档，才能永久删除。")
    paths = list(dict.fromkeys([
        *[
            str(item)
            for item in task.get("result", {}).get("source_snapshot_paths", [])
            if str(item)
        ],
        *[
            str(item.get("relative_path") or "")
            for item in task.get("result", {}).get("fetched_sources", [])
            if str(item.get("relative_path") or "")
        ],
    ]))
    deleted = delete_archived_web_research_task(project_name, task_id)
    if deleted and paths:
        delete_imported_web_pages(
            project_name,
            paths,
            research_task_id=task_id,
            build_vectors=True,
        )
    return deleted


def _claim_for_execution(
    project_name: str,
    task_id: str,
    worker_id: str,
    lease_seconds: int,
    lease_already_claimed: bool,
) -> dict:
    if lease_already_claimed:
        control = load_web_research_task_control(project_name, task_id, worker_id)
        if not control.get("owned") or control.get("status") != "running":
            raise WebResearchTaskLeaseLost(f"网络研究任务租约已失效：{task_id}")
        return _require_task(project_name, task_id)
    existing = _require_task(project_name, task_id)
    if existing.get("status") in {"paused", "failed", "completed_with_errors"} and not existing.get("worker_id"):
        resume_web_research_task(project_name, task_id)
    claimed = claim_web_research_task(
        project_name,
        task_id,
        worker_id,
        lease_seconds=lease_seconds,
    )
    if not claimed:
        existing = _require_task(project_name, task_id)
        if existing.get("status") == "completed":
            return existing
        raise WebResearchTaskLeaseUnavailable(f"网络研究任务当前不可领取：{task_id}")
    return claimed


def _save_owned(project_name: str, task: dict, worker_id: str) -> dict:
    saved = save_web_research_task(project_name, task)
    control = load_web_research_task_control(
        project_name,
        str(task.get("task_id") or task.get("run_id") or ""),
        worker_id,
    )
    if (
        str(saved.get("worker_id") or "") != worker_id
        or saved.get("status") != "running"
        or not control.get("owned")
    ):
        raise WebResearchTaskLeaseLost("网络研究任务租约已被其它 worker 接管。")
    return saved


def _finalize_owned(project_name: str, task: dict, worker_id: str) -> dict:
    expected_status = str(task.get("status") or "")
    saved = finalize_web_research_task(project_name, task, worker_id)
    requested = str(saved.get("control_requested") or "")
    if saved.get("worker_id") == worker_id and saved.get("status") == "running" and requested in {"pause", "cancel"}:
        if expected_status in {"completed", "completed_with_errors"}:
            saved = finalize_web_research_task(
                project_name,
                task,
                worker_id,
                acknowledged_control=requested,
            )
        else:
            controlled_status = "paused" if requested == "pause" else "cancelled"
            controlled = set_web_research_task_status(task, controlled_status)
            saved = finalize_web_research_task(project_name, controlled, worker_id)
            expected_status = controlled_status
    if saved.get("worker_id") or saved.get("status") != expected_status:
        raise WebResearchTaskLeaseLost("旧 worker 无权结束网络研究任务。")
    return saved


def run_web_research_task(
    project_name: str,
    task_id: str,
    *,
    worker_id: str = "",
    lease_seconds: int = DEFAULT_WEB_RESEARCH_LEASE_SECONDS,
    lease_already_claimed: bool = False,
    planner_func=plan_web_research_with_llm,
    graph_builder=build_web_research_graph,
    fetcher=fetch_web_page,
    importer=import_fetched_web_pages,
    page_loader=load_imported_web_page,
    extractor=extract_claims_from_web_page,
    verifier=verify_research_claims,
    rebuild_func=rebuild_retrieval_assets,
) -> tuple[dict, dict]:
    owner = worker_id or f"manual-web:{os.getpid()}:{uuid4().hex[:10]}"
    task = _claim_for_execution(project_name, task_id, owner, lease_seconds, lease_already_claimed)
    if task.get("status") == "completed" and not task.get("worker_id"):
        return task, dict(task.get("result") or {})
    recovery_time = datetime.now(timezone.utc).isoformat()
    for step in task.get("steps", {}).values():
        if isinstance(step, dict) and step.get("status") == "running":
            step["status"] = "pending"
            step["updated_at"] = recovery_time
    task = set_web_research_task_status(task, "running", message="正在执行网络研究。")
    task = _save_owned(project_name, task, owner)
    configuration = dict(task.get("configuration") or {})
    task_holder = {"task": task}

    def checkpoint(message: str) -> dict:
        current = normalize_web_research_task(task_holder["task"])
        current["current_message"] = message
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        task_holder["task"] = _save_owned(project_name, current, owner)
        control = load_web_research_task_control(project_name, task_id, owner)
        if not control.get("owned"):
            raise WebResearchTaskLeaseLost("网络研究任务租约已失效。")
        requested = str(control.get("control_requested") or "")
        if requested in {"pause", "cancel"}:
            raise _WebResearchControlSignal(requested)
        return task_holder["task"]

    def begin_stage(name: str, message: str) -> None:
        current = update_web_research_stage(task_holder["task"], name, "running")
        task_holder["task"] = current
        checkpoint(message)

    def finish_stage(name: str, output: dict, message: str) -> None:
        current = update_web_research_stage(task_holder["task"], name, "completed", output=output)
        task_holder["task"] = current
        checkpoint(message)

    active_stage = ""
    try:
        result = dict(task_holder["task"].get("result") or {})

        if task_holder["task"]["steps"]["plan"]["status"] != "completed":
            active_stage = "plan"
            begin_stage("plan", "研究规划 Agent 正在拆分来源角色和查询。")
            if configuration.get("use_llm_planner", True):
                with llm_usage_scope(
                    project_name=project_name,
                    story_id=str(task_holder["task"].get("story_id") or "default"),
                    task_id=task_id,
                    workflow_run_id=task_id,
                    operation="web_research.plan",
                    agent_role="planner",
                ):
                    plan = planner_func(
                        task_holder["task"]["topic"],
                        list(configuration.get("source_kinds") or []),
                        int(configuration.get("max_results_per_branch") or 5),
                        objective=task_holder["task"].get("objective", ""),
                        official_domains=list(configuration.get("official_domains") or []),
                        max_pages=int(configuration.get("max_pages") or 8),
                    )
            else:
                plan = build_default_web_research_plan(
                    task_holder["task"]["topic"],
                    list(configuration.get("source_kinds") or []),
                    int(configuration.get("max_results_per_branch") or 5),
                )
                plan.max_pages = int(configuration.get("max_pages") or plan.max_pages)
                official_domains = list(configuration.get("official_domains") or [])
                for branch in plan.branches:
                    if branch.source_kind == "official":
                        branch.preferred_domains = official_domains
            result["plan"] = plan.model_dump()
            task_holder["task"]["result"] = result
            finish_stage("plan", {"branch_count": len(plan.branches)}, "研究计划已保存。")
        plan = WebResearchPlan.model_validate(result["plan"])

        if task_holder["task"]["steps"]["search"]["status"] != "completed":
            active_stage = "search"
            begin_stage("search", "多个来源采集 Agent 正在并行搜索。")
            graph = graph_builder(planner=lambda *_args: plan)
            graph_state = graph.invoke(
                {
                    "topic": task_holder["task"]["topic"],
                    "source_kinds": list(configuration.get("source_kinds") or []),
                    "provider": "brave",
                    "language": str(configuration.get("language") or "zh-hans"),
                    "freshness": str(configuration.get("freshness") or ""),
                    "max_results_per_branch": int(configuration.get("max_results_per_branch") or 5),
                    "branch_results": [],
                    "errors": [],
                },
                {"max_concurrency": int(configuration.get("max_concurrency") or 3)},
            )
            result["branch_results"] = list(graph_state.get("branch_results") or [])
            result["search_hits"] = list(graph_state.get("search_hits") or [])
            result["search_errors"] = list(graph_state.get("errors") or [])
            result["selected_hits"] = select_research_hits(
                result["search_hits"],
                int(configuration.get("max_pages") or plan.max_pages),
            )
            if not result["selected_hits"]:
                raise RuntimeError("搜索没有返回可供抓取的公开网页。")
            task_holder["task"]["result"] = result
            finish_stage(
                "search",
                {
                    "hit_count": len(result["search_hits"]),
                    "selected_count": len(result["selected_hits"]),
                    "errors": result["search_errors"],
                },
                "搜索完成，已按来源角色和域名多样性选择网页。",
            )

        if task_holder["task"]["steps"]["fetch"]["status"] != "completed":
            active_stage = "fetch"
            begin_stage("fetch", "安全抓取 Agent 正在下载公开网页。")
            fetched_sources = list(result.get("fetched_sources") or [])
            existing_urls = {
                str(existing_url)
                for item in fetched_sources
                for existing_url in (
                    list(item.get("requested_urls") or [])
                    or [item.get("requested_url") or item.get("url") or ""]
                )
                if str(existing_url)
            }
            existing_by_final_url = {
                str(item.get("url") or ""): item
                for item in fetched_sources
                if str(item.get("url") or "")
            }
            fetch_errors = list(result.get("fetch_errors") or [])
            for hit in result.get("selected_hits", []):
                url = str(hit.get("url") or "")
                if not url or url in existing_urls:
                    continue
                try:
                    page = fetcher(url)
                    existing_source = existing_by_final_url.get(page.final_url)
                    hit_source_kinds = [
                        str(item)
                        for item in (hit.get("source_kinds") or [])
                        if str(item)
                    ]
                    combined_source_kinds = list(dict.fromkeys([
                        *list(
                            (existing_source or {}).get("source_kinds")
                            or [(existing_source or {}).get("source_kind")]
                        ),
                        *hit_source_kinds,
                    ]))
                    combined_source_kinds = [item for item in combined_source_kinds if item]
                    assessment = assess_web_source(
                        page.final_url,
                        combined_source_kinds,
                        official_domains=list(configuration.get("official_domains") or []),
                    )
                    imported = importer(
                        project_name,
                        [page],
                        query=task_holder["task"]["topic"],
                        provider="brave",
                        scope=str(configuration.get("scope") or "reference"),
                        authority=assessment.authority,
                        build_vectors=False,
                        rebuild_assets=False,
                        extra_metadata={
                            "research_task_id": task_id,
                            "source_kind": assessment.source_kind,
                            "authority_assessment": assessment.model_dump(),
                            "retrieval_status": "quarantine",
                            "untrusted_web_content": True,
                            "story_id": str(task_holder["task"].get("story_id") or ""),
                        },
                    )
                    if imported:
                        requested_urls = list(dict.fromkeys([
                            *list((existing_source or {}).get("requested_urls") or []),
                            str((existing_source or {}).get("requested_url") or ""),
                            url,
                        ]))
                        requested_urls = [item for item in requested_urls if item]
                        row = {
                            **imported[0],
                            "requested_url": requested_urls[0],
                            "requested_urls": requested_urls,
                            "source_kinds": combined_source_kinds,
                            "source_kind": assessment.source_kind,
                            "authority": assessment.authority,
                            "authority_assessment": assessment.model_dump(),
                        }
                        if existing_source is None:
                            fetched_sources.append(row)
                            existing_by_final_url[page.final_url] = row
                        else:
                            existing_source.clear()
                            existing_source.update(row)
                        existing_urls.add(url)
                        result["source_snapshot_paths"] = [item for item in dict.fromkeys([
                            *list(result.get("source_snapshot_paths") or []),
                            str(row.get("relative_path") or ""),
                        ]) if item]
                except Exception as exc:
                    fetch_errors.append({"url": url, "error": str(exc)})
                result["fetched_sources"] = fetched_sources
                result["fetch_errors"] = fetch_errors
                task_holder["task"]["result"] = result
                checkpoint(f"已处理 {len(existing_urls)}/{len(result.get('selected_hits', []))} 个候选网页。")
            if not fetched_sources:
                raise RuntimeError("所有候选网页均抓取失败。")
            with llm_usage_scope(
                project_name=project_name,
                story_id=str(task_holder["task"].get("story_id") or "default"),
                task_id=task_id,
                workflow_run_id=task_id,
                operation="web_research.index",
                agent_role="indexer",
            ):
                rebuild_func(project_name, build_vectors=True)
            finish_stage(
                "fetch",
                {"source_count": len(fetched_sources), "errors": fetch_errors},
                "网页原文已持久化并更新检索资产。",
            )

        if task_holder["task"]["steps"]["extract"]["status"] != "completed":
            active_stage = "extract"
            begin_stage("extract", "事实提取 Agent 正在生成带原文引文的候选主张。")
            claims = list(result.get("claims") or [])
            page_extractions = list(result.get("page_extractions") or [])
            extracted_source_keys = {
                str(item.get("source_relative_path") or "")
                or f"{item.get('url', '')}|{item.get('content_hash', '')}"
                for item in page_extractions
            }
            extraction_errors = list(result.get("extraction_errors") or [])
            for source in result.get("fetched_sources", []):
                content_hash = str(source.get("content_hash") or "")
                source_relative_path = str(source.get("relative_path") or "")
                source_key = source_relative_path or f"{source.get('url', '')}|{content_hash}"
                if source_key in extracted_source_keys:
                    continue
                try:
                    page = page_loader(project_name, str(source.get("relative_path") or ""))
                    with llm_usage_scope(
                        project_name=project_name,
                        story_id=str(task_holder["task"].get("story_id") or "default"),
                        task_id=task_id,
                        workflow_run_id=task_id,
                        operation="web_research.extract",
                        agent_role="extractor",
                    ):
                        extraction = extractor(
                            page,
                            source_kind=str(source.get("source_kind") or "general"),
                            authority=str(source.get("authority") or "unknown"),
                            enabled_categories=list(configuration.get("enabled_categories") or DEFAULT_RESEARCH_CATEGORIES),
                            topic=task_holder["task"]["topic"],
                            objective=task_holder["task"].get("objective", ""),
                            max_chars=int(configuration.get("max_chars_per_page") or 30000),
                            max_claims=int(configuration.get("max_claims_per_page") or 20),
                        )
                    claims.extend(item.model_dump() for item in extraction.claims)
                    page_extractions.append(
                        {
                            "url": page.final_url,
                            "source_relative_path": source_relative_path,
                            "content_hash": content_hash,
                            "claim_count": len(extraction.claims),
                            "candidate_claim_count": extraction.candidate_claim_count,
                            "rejected_claim_count": extraction.rejected_claim_count,
                            "notes": extraction.notes,
                        }
                    )
                    extracted_source_keys.add(source_key)
                except Exception as exc:
                    extraction_errors.append({"url": source.get("url", ""), "error": str(exc)})
                result["claims"] = claims
                result["page_extractions"] = page_extractions
                result["extraction_errors"] = extraction_errors
                task_holder["task"]["result"] = result
                checkpoint(f"已从 {len(page_extractions)} 个网页提取可追溯主张。")
            if not page_extractions and result.get("fetched_sources"):
                raise RuntimeError("所有网页的事实提取均失败。")
            finish_stage(
                "extract",
                {"claim_count": len(claims), "errors": extraction_errors},
                "候选主张提取完成，无法定位原文的引文已被剔除。",
            )

        if task_holder["task"]["steps"]["verify"]["status"] != "completed":
            active_stage = "verify"
            begin_stage("verify", "验证 Agent 正在合并同义事实并识别冲突。")
            with llm_usage_scope(
                project_name=project_name,
                story_id=str(task_holder["task"].get("story_id") or "default"),
                task_id=task_id,
                workflow_run_id=task_id,
                operation="web_research.verify",
                agent_role="verifier",
            ):
                verification = verifier(
                    list(result.get("claims") or []),
                    use_llm=bool(configuration.get("use_llm_verifier", True)),
                )
            if not isinstance(verification, WebResearchVerificationResult):
                verification = WebResearchVerificationResult.model_validate(verification)
            verified_claims = build_verified_research_claims(
                list(result.get("claims") or []),
                verification,
            )
            result["verification"] = verification.model_dump()
            result["verified_claims"] = [item.model_dump() for item in verified_claims]
            task_holder["task"]["result"] = result
            finish_stage(
                "verify",
                {
                    "verified_count": len(verified_claims),
                    "contested_count": sum(item.verification_status == "contested" for item in verified_claims),
                },
                "交叉验证完成，结果等待人工选择进入待审核设定。",
            )

        if task_holder["task"]["steps"]["evaluate"]["status"] != "completed":
            active_stage = "evaluate"
            begin_stage("evaluate", "正在计算研究覆盖率和证据质量指标。")
            evaluation = evaluate_web_research_state(task_holder["task"])
            result["evaluation"] = evaluation.model_dump()
            task_holder["task"]["result"] = result
            finish_stage("evaluate", evaluation.model_dump(), "网络研究评测完成。")

        errors = [
            *list(result.get("search_errors") or []),
            *list(result.get("fetch_errors") or []),
            *list(result.get("extraction_errors") or []),
        ]
        final_status = "completed_with_errors" if errors else "completed"
        task_holder["task"].pop("retry_from_stage", None)
        task_holder["task"]["result"] = result
        final = set_web_research_task_status(
            task_holder["task"],
            final_status,
            message="网络研究已完成，结果等待人工审核。",
        )
        return _finalize_owned(project_name, final, owner), result
    except _WebResearchControlSignal as signal:
        final_status = "paused" if signal.control == "pause" else "cancelled"
        final = set_web_research_task_status(task_holder["task"], final_status)
        return _finalize_owned(project_name, final, owner), dict(final.get("result") or {})
    except WebResearchTaskLeaseLost:
        raise
    except Exception as exc:
        current = normalize_web_research_task(task_holder["task"])
        if active_stage in WEB_RESEARCH_STAGE_NAMES:
            current = update_web_research_stage(current, active_stage, "failed", error=str(exc))
        current = set_web_research_task_status(
            current,
            "failed",
            message="网络研究执行中断，可从失败阶段重试。",
            error=str(exc),
        )
        _finalize_owned(project_name, current, owner)
        raise


def queue_web_research_claims_for_review(
    project_name: str,
    task_id: str,
    claim_ids: list[str],
) -> dict:
    """Queue selected verified claims; formal knowledge still requires human confirmation."""

    task = _require_task(project_name, task_id)
    _require_not_archived(task, "提交审核")
    if task.get("status") not in {"completed", "completed_with_errors"}:
        raise ValueError("网络研究任务尚未完成，不能提交审核。")
    selected_ids = {str(item) for item in claim_ids if str(item)}
    verified_rows = [
        item for item in task.get("result", {}).get("verified_claims", [])
        if str(item.get("claim_id") or "") in selected_ids
    ]
    if not verified_rows:
        raise ValueError("请至少选择一条研究结论。")
    queued_count = 0
    queued_ids: list[str] = []
    grouped: dict[str, list[dict]] = {}
    for row in verified_rows:
        pending = verified_claim_to_pending_item(
            row,
            task_id,
            story_id=str(task.get("story_id") or ""),
        )
        grouped.setdefault(str(row.get("authority") or "unknown"), []).append(pending)
        queued_ids.append(str(pending["pending_id"]))
    scope = str(task.get("configuration", {}).get("scope") or "reference")
    for authority, items in grouped.items():
        queued_count += queue_pending_knowledge_items(
            project_name,
            items,
            scope=scope,
            authority=authority,
            source_title=task.get("title", "网络研究"),
            source_origin=f"web-research:{task_id}",
        )
    result = dict(task.get("result") or {})
    result["queued_pending_ids"] = list(dict.fromkeys([*result.get("queued_pending_ids", []), *queued_ids]))
    task["result"] = result
    save_web_research_task(project_name, task)
    return {"queued_count": queued_count, "pending_ids": queued_ids}


def activate_web_research_sources(project_name: str, task_id: str) -> dict:
    """Explicitly release fetched raw pages from quarantine into retrieval."""

    task = _require_task(project_name, task_id)
    _require_not_archived(task, "启用网页原文")
    if task.get("status") not in {"completed", "completed_with_errors"}:
        raise ValueError("网络研究任务尚未完成，不能启用网页原文检索。")
    sources = list(task.get("result", {}).get("fetched_sources") or [])
    paths = list(dict.fromkeys(
        str(item.get("relative_path") or "")
        for item in sources
        if str(item.get("relative_path") or "")
    ))
    if not paths:
        raise ValueError("任务没有可启用的网页来源。")
    changed = set_imported_web_pages_retrieval_status(
        project_name,
        paths,
        status="active",
        build_vectors=True,
        research_task_id=task_id,
    )
    statuses = get_imported_web_pages_retrieval_statuses(
        project_name,
        paths,
        research_task_id=task_id,
    )
    if len(statuses) != len(paths) or any(value != "active" for value in statuses.values()):
        raise RuntimeError("部分网页来源缺失或不属于当前任务，未更新任务激活状态。")
    result = dict(task.get("result") or {})
    result["raw_sources_retrieval_status"] = "active"
    task["result"] = result
    save_web_research_task(project_name, task)
    return {"changed_count": changed, "source_count": len(paths)}


def quarantine_web_research_sources(project_name: str, task_id: str) -> dict:
    """Remove task-owned raw web pages from retrieval without deleting snapshots."""

    task = _require_task(project_name, task_id)
    _require_not_archived(task, "隔离网页原文")
    sources = list(task.get("result", {}).get("fetched_sources") or [])
    paths = list(dict.fromkeys(
        str(item.get("relative_path") or "")
        for item in sources
        if str(item.get("relative_path") or "")
    ))
    if not paths:
        raise ValueError("任务没有可隔离的网页来源。")
    changed = set_imported_web_pages_retrieval_status(
        project_name,
        paths,
        status="quarantine",
        build_vectors=True,
        research_task_id=task_id,
    )
    statuses = get_imported_web_pages_retrieval_statuses(
        project_name,
        paths,
        research_task_id=task_id,
    )
    if len(statuses) != len(paths) or any(value != "quarantine" for value in statuses.values()):
        raise RuntimeError("部分网页来源缺失或不属于当前任务，未更新任务隔离状态。")
    result = dict(task.get("result") or {})
    result["raw_sources_retrieval_status"] = "quarantine"
    task["result"] = result
    save_web_research_task(project_name, task)
    return {"changed_count": changed, "source_count": len(paths)}
