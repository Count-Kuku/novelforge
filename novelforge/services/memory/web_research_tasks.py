"""SQLite-backed persistence facade for durable web-research tasks."""

from __future__ import annotations

from novelforge.domain.web_research_tasks import (
    WEB_RESEARCH_WORKFLOW_TYPE,
    normalize_web_research_task,
)
from novelforge.services import memory as _memory_api
from storage.repositories.durable_tasks import (
    claim_durable_task_row,
    delete_archived_durable_task_row,
    finalize_durable_task_row,
    heartbeat_durable_task_row,
    list_durable_task_rows,
    load_durable_task_control_row,
    load_durable_task_row,
    persist_durable_task_row,
    request_durable_task_control_row,
    set_durable_task_archived_row,
    settle_stale_durable_task_controls_row,
)


def save_web_research_task(project_name: str, task: dict) -> dict:
    normalized = normalize_web_research_task(
        {
            **(task or {}),
            "updated_at": _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(),
        }
    )
    persisted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: persist_durable_task_row(
            conn,
            task={**normalized, "project_name": project_name},
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            expected_worker_id=str(normalized.get("worker_id") or ""),
        ),
        "web research task snapshot",
    )
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "project_maintenance":
        raise ValueError("项目正在重命名或删除，暂时不能创建网络研究任务。")
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "run_id":
        raise ValueError("网络研究任务 ID 已被其它工作流占用。")
    if persisted:
        return normalize_web_research_task(persisted)
    if normalized.get("worker_id"):
        return {}
    latest = load_web_research_task(project_name, normalized["task_id"])
    if latest:
        return latest
    raise RuntimeError("网络研究任务未能写入项目数据库。")


def finalize_web_research_task(
    project_name: str,
    task: dict,
    worker_id: str,
    *,
    acknowledged_control: str = "",
) -> dict:
    normalized = normalize_web_research_task(task)
    persisted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: finalize_durable_task_row(
            conn,
            task={**normalized, "project_name": project_name},
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            worker_id=str(worker_id),
            acknowledged_control=str(acknowledged_control or ""),
        ),
        "web research task finalize",
    )
    if persisted:
        return normalize_web_research_task(persisted)
    latest = load_web_research_task(project_name, normalized["task_id"])
    if latest:
        return latest
    raise RuntimeError("网络研究任务终态未能写入项目数据库。")


def load_web_research_task(project_name: str, task_id: str) -> dict:
    payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_durable_task_row(
            conn,
            task_id=str(task_id),
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
        ),
        "web research task",
    )
    return normalize_web_research_task(payload) if payload else {}


def list_web_research_tasks(
    project_name: str,
    story_id: str = "",
    *,
    statuses: list[str] | None = None,
    include_archived: bool = False,
) -> list[dict]:
    payloads = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: list_durable_task_rows(
            conn,
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            statuses=statuses,
            include_archived=include_archived,
        ),
        "web research tasks",
    ) or []
    clean_story_id = str(story_id or "")
    tasks = [normalize_web_research_task(item) for item in payloads]
    return [item for item in tasks if not clean_story_id or item.get("story_id") == clean_story_id]


def claim_next_web_research_task(project_name: str, worker_id: str, *, lease_seconds: int) -> dict:
    payload = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: claim_durable_task_row(
            conn,
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ),
        "web research task claim",
    )
    return normalize_web_research_task(payload) if payload else {}


def claim_web_research_task(
    project_name: str,
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> dict:
    payload = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: claim_durable_task_row(
            conn,
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            task_id=task_id,
        ),
        "web research task claim",
    )
    return normalize_web_research_task(payload) if payload else {}


def heartbeat_web_research_task(
    project_name: str,
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> bool:
    return bool(
        _memory_api._mutate_workflow_in_db(
            project_name,
            lambda conn: heartbeat_durable_task_row(
                conn,
                task_id=task_id,
                workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            ),
            "web research task heartbeat",
        )
    )


def load_web_research_task_control(project_name: str, task_id: str, worker_id: str = "") -> dict:
    return _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_durable_task_control_row(
            conn,
            task_id=task_id,
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            worker_id=worker_id,
        ),
        "web research task control",
    ) or {}


def request_web_research_task_control(project_name: str, task_id: str, control: str) -> dict:
    return _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: request_durable_task_control_row(
            conn,
            task_id=task_id,
            workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            control=control,
        ),
        "web research task control",
    ) or {}


def settle_stale_web_research_controls(project_name: str) -> int:
    return int(
        _memory_api._mutate_workflow_in_db(
            project_name,
            lambda conn: settle_stale_durable_task_controls_row(
                conn,
                workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            ),
            "stale web research controls",
        )
        or 0
    )


def set_web_research_task_archived(project_name: str, task_id: str, archived: bool) -> bool:
    return bool(
        _memory_api._mutate_workflow_in_db(
            project_name,
            lambda conn: set_durable_task_archived_row(
                conn,
                task_id=task_id,
                workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
                archived=archived,
            ),
            "web research task archive",
        )
    )


def delete_archived_web_research_task(project_name: str, task_id: str) -> bool:
    return bool(
        _memory_api._mutate_workflow_in_db(
            project_name,
            lambda conn: delete_archived_durable_task_row(
                conn,
                task_id=task_id,
                workflow_type=WEB_RESEARCH_WORKFLOW_TYPE,
            ),
            "archived web research task deletion",
        )
    )
