"""SQLite-backed runtime persistence for source-ingestion tasks."""
from __future__ import annotations

from datetime import datetime

from novelforge.domain.ingestion_tasks import normalize_ingestion_task
from novelforge.services import memory as _memory_api
from storage.repositories.ingestion_tasks import (
    finalize_source_ingestion_task_row,
    persist_source_ingestion_task_row,
)


def _source_ingestion_task_snapshot(project_name: str, task: dict) -> dict:
    normalized = normalize_ingestion_task(task)
    steps = {}
    for item in normalized.get("items", []):
        item_id = str(item.get("item_id") or f"segment_{item.get('segment_index', 0)}")
        steps[item_id] = {**item, "step_name": item_id}
    return {
        **normalized,
        "project_name": project_name,
        "errors": [normalized.get("last_error")] if normalized.get("last_error") else [],
        "steps": steps,
    }


def save_source_ingestion_task(project_name: str, task: dict) -> dict:
    normalized = normalize_ingestion_task({
        **(task or {}),
        "updated_at": _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(),
    })
    snapshot = _source_ingestion_task_snapshot(project_name, normalized)
    expected_worker_id = str(normalized.get("worker_id") or "")
    persisted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: persist_source_ingestion_task_row(
            conn,
            task=snapshot,
            story_id=normalized.get("story_id") or None,
            expected_worker_id=expected_worker_id,
        ),
        "source ingestion task snapshot",
    )
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "unfinished_batch":
        conflict_task_id = str(persisted.get("conflict_task_id") or "")
        raise ValueError(f"该资料批次已有未完成任务：{conflict_task_id}")
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "project_maintenance":
        raise ValueError("项目正在重命名或删除，暂时不能创建资料任务。")
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "batch_missing":
        raise ValueError("资料批次不存在或已被删除，不能创建资料任务。")
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "batch_changed":
        raise ValueError("资料批次已发生变化，所选片段不再有效；请刷新批次后重新创建任务。")
    if isinstance(persisted, dict) and persisted.get("persistence_conflict") == "run_id":
        workflow_type = str(persisted.get("conflicting_workflow_type") or "unknown")
        raise ValueError(f"资料任务 ID 已被其他工作流占用：{workflow_type}")
    if persisted:
        return normalize_ingestion_task(persisted)
    # A lost/stolen lease must never overwrite the authoritative row. Returning
    # the latest snapshot lets existing callers converge without a second write.
    latest = load_source_ingestion_task(project_name, normalized["task_id"])
    if latest:
        return latest
    if not _memory_api.project_is_discoverable(project_name):
        raise FileNotFoundError(f"项目不存在或已被移动：{project_name}")
    raise RuntimeError("资料任务未能写入项目数据库。")


def finalize_source_ingestion_task(
    project_name: str,
    task: dict,
    worker_id: str,
    *,
    acknowledged_control: str = "",
) -> dict:
    """Persist a terminal worker snapshot and clear its lease atomically."""
    normalized = normalize_ingestion_task(task)
    snapshot = _source_ingestion_task_snapshot(project_name, normalized)
    persisted = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: finalize_source_ingestion_task_row(
            conn,
            task=snapshot,
            worker_id=str(worker_id),
            story_id=normalized.get("story_id") or None,
            acknowledged_control=str(acknowledged_control or ""),
        ),
        "source ingestion task finalize",
    )
    if persisted:
        return normalize_ingestion_task(persisted)
    latest = load_source_ingestion_task(project_name, normalized["task_id"])
    if latest:
        return latest
    if not _memory_api.project_is_discoverable(project_name):
        raise FileNotFoundError(f"项目不存在或已被移动：{project_name}")
    raise RuntimeError("资料任务终态未能写入项目数据库。")


def load_source_ingestion_task(project_name: str, task_id: str) -> dict:
    payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_source_ingestion_task_row(conn, task_id),
        "source ingestion task",
    )
    return normalize_ingestion_task(payload) if payload else {}


def list_source_ingestion_tasks(
    project_name: str,
    story_id: str = "",
    *,
    statuses: list[str] | None = None,
    include_archived: bool = False,
) -> list[dict]:
    payloads = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.list_source_ingestion_task_rows(
            conn,
            statuses=statuses,
            include_archived=include_archived,
        ),
        "source ingestion tasks",
    )
    clean_story_id = str(story_id or "")
    tasks = []
    for payload in payloads or []:
        task = normalize_ingestion_task(payload)
        if clean_story_id and str(task.get("story_id") or "") != clean_story_id:
            continue
        tasks.append(task)
    return tasks


def claim_next_source_ingestion_task(
    project_name: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> dict:
    payload = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.claim_next_source_ingestion_task_row(
            conn,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ),
        "source ingestion task claim",
    )
    return normalize_ingestion_task(payload) if payload else {}


def claim_source_ingestion_task(
    project_name: str,
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> dict:
    payload = _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.claim_source_ingestion_task_row(
            conn,
            task_id=task_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ),
        "source ingestion task claim",
    )
    return normalize_ingestion_task(payload) if payload else {}


def heartbeat_source_ingestion_task(
    project_name: str,
    task_id: str,
    worker_id: str,
    *,
    lease_seconds: int,
) -> bool:
    return bool(_memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.heartbeat_source_ingestion_task_row(
            conn,
            task_id=task_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        ),
        "source ingestion task heartbeat",
    ))


def load_source_ingestion_task_control(project_name: str, task_id: str, worker_id: str = "") -> dict:
    return _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_source_ingestion_task_control_row(
            conn,
            task_id=task_id,
            worker_id=worker_id,
        ),
        "source ingestion task control",
    ) or {}


def request_source_ingestion_task_control(project_name: str, task_id: str, control: str) -> dict:
    return _memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.request_source_ingestion_task_control_row(
            conn,
            task_id=task_id,
            control=control,
        ),
        "source ingestion task control",
    ) or {}


def release_source_ingestion_task_lease(
    project_name: str,
    task_id: str,
    worker_id: str,
    status: str,
) -> bool:
    return bool(_memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.release_source_ingestion_task_lease_row(
            conn,
            task_id=task_id,
            worker_id=worker_id,
            status=status,
        ),
        "source ingestion task lease release",
    ))


def settle_stale_source_ingestion_controls(project_name: str) -> int:
    return int(_memory_api._mutate_workflow_in_db(
        project_name,
        _memory_api.settle_stale_source_ingestion_controls_row,
        "stale source ingestion controls",
    ) or 0)


def set_source_ingestion_task_archived(project_name: str, task_id: str, archived: bool) -> bool:
    return bool(_memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.set_source_ingestion_task_archived_row(
            conn,
            task_id=task_id,
            archived=archived,
        ),
        "source ingestion task archive",
    ))


def delete_archived_source_ingestion_task(project_name: str, task_id: str) -> bool:
    return bool(_memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.delete_archived_source_ingestion_task_row(conn, task_id=task_id),
        "archived source ingestion task deletion",
    ))


def cleanup_archived_source_ingestion_tasks(project_name: str, *, before: datetime) -> int:
    return int(_memory_api._mutate_workflow_in_db(
        project_name,
        lambda conn: _memory_api.cleanup_archived_source_ingestion_task_rows(conn, before=before),
        "archived source ingestion task cleanup",
    ) or 0)
