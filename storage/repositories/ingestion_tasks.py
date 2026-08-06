from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .ingestion_batch_mutations import (
    SOURCE_INGESTION_WORKFLOW_TYPE,
    ingestion_task_batch_conflict,
    unfinished_batch_task_id,
)
from .workflows import sync_workflow_run_snapshot


CLAIMABLE_STATUSES = {"queued", "running"}
ARCHIVABLE_STATUSES = {"failed", "completed_with_errors", "completed", "cancelled"}
CONTROL_REQUESTS = {"pause", "cancel", "resume"}
WORKER_FINAL_STATUSES = {"paused", "failed", "completed_with_errors", "completed", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_loads_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _row_value(row: sqlite3.Row | tuple, key: str, index: int):
    return row[key] if isinstance(row, sqlite3.Row) else row[index]


def _project_is_in_maintenance(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM project_meta WHERE maintenance_mode = 1 LIMIT 1"
    ).fetchone()
    return row is not None


def _task_from_row(row: sqlite3.Row | tuple | None) -> dict:
    if row is None:
        return {}
    payload = _json_loads_dict(_row_value(row, "output_json", 4))
    payload.update(
        {
            "task_id": str(_row_value(row, "run_id", 0)),
            "run_id": str(_row_value(row, "run_id", 0)),
            "workflow_type": str(_row_value(row, "workflow_type", 2)),
            "status": str(_row_value(row, "status", 3)),
            "story_id": str(_row_value(row, "story_id", 1) or payload.get("story_id") or ""),
            "updated_at": str(_row_value(row, "updated_at", 5) or payload.get("updated_at") or ""),
            "worker_id": str(_row_value(row, "worker_id", 6) or ""),
            "lease_expires_at": str(_row_value(row, "lease_expires_at", 7) or ""),
            "heartbeat_at": str(_row_value(row, "heartbeat_at", 8) or ""),
            "control_requested": str(_row_value(row, "control_requested", 9) or ""),
            "priority": int(_row_value(row, "priority", 10) or 0),
            "archived_at": str(_row_value(row, "archived_at", 11) or ""),
        }
    )
    return payload


def _task_select_sql(where_sql: str) -> str:
    return f"""
        SELECT run_id, story_id, workflow_type, status, output_json,
               updated_at, worker_id, lease_expires_at, heartbeat_at,
               control_requested, priority, archived_at
        FROM workflow_runs
        WHERE {where_sql}
    """


def _sync_source_ingestion_task_snapshot(
    conn: sqlite3.Connection,
    *,
    task: dict,
    story_id: str | None = None,
) -> dict:
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    if not task_id:
        raise ValueError("Source-ingestion task ID cannot be empty.")
    sync_workflow_run_snapshot(
        conn,
        run_id=task_id,
        payload=task,
        story_id=story_id or task.get("story_id"),
    )
    estimate = dict(task.get("estimate") or {})
    updated_at = str(task.get("updated_at") or _iso(_now()))
    conn.execute(
        """
        UPDATE workflow_runs
        SET updated_at = ?,
            priority = ?,
            estimated_input_tokens = ?,
            estimated_output_tokens = ?,
            estimated_embedding_tokens = ?,
            estimated_cost_usd = ?
        WHERE run_id = ? AND workflow_type = ?
        """,
        (
            updated_at,
            int(task.get("priority") or 0),
            int(estimate.get("estimated_input_tokens") or 0),
            int(estimate.get("estimated_output_tokens") or 0),
            int(estimate.get("estimated_embedding_tokens") or 0),
            float(estimate.get("estimated_cost_usd") or 0.0),
            task_id,
            SOURCE_INGESTION_WORKFLOW_TYPE,
        ),
    )
    return task


def _runtime_row(conn: sqlite3.Connection, task_id: str):
    return conn.execute(
        """
        SELECT status, worker_id, lease_expires_at, archived_at, control_requested
        FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ?
        """,
        (str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
    ).fetchone()


def _worker_owns_live_running_row(
    row: sqlite3.Row | tuple | None,
    *,
    worker_id: str,
    now_iso: str,
) -> bool:
    if row is None:
        return False
    return (
        bool(str(worker_id or ""))
        and str(_row_value(row, "status", 0) or "") == "running"
        and str(_row_value(row, "worker_id", 1) or "") == str(worker_id)
        and str(_row_value(row, "lease_expires_at", 2) or "") > now_iso
        and not _row_value(row, "archived_at", 3)
    )


def _finalize_owned_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    worker_id: str,
    story_id: str | None,
    now_iso: str,
    control_requested: str = "",
    acknowledged_control: str = "",
) -> dict:
    final_status = str(task.get("status") or "")
    if final_status not in WORKER_FINAL_STATUSES:
        return {}
    clean_control = str(control_requested or "")
    matching_control = {"paused": "pause", "cancelled": "cancel"}.get(final_status, "")
    completion_acknowledged = (
        final_status in {"completed", "completed_with_errors"}
        and str(acknowledged_control or "") == clean_control
    )
    if clean_control and matching_control != clean_control and not completion_acknowledged:
        return load_source_ingestion_task_row(
            conn,
            str(task.get("task_id") or task.get("run_id") or ""),
        )
    final_task = {
        **task,
        "worker_id": "",
        "heartbeat_at": "",
        "lease_expires_at": "",
        "control_requested": "",
        "updated_at": str(task.get("updated_at") or now_iso),
    }
    _sync_source_ingestion_task_snapshot(conn, task=final_task, story_id=story_id)
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
            control_requested = '', updated_at = ?
        WHERE run_id = ? AND workflow_type = ? AND worker_id = ?
          AND COALESCE(control_requested, '') = ?
        """,
        (
            str(final_task.get("updated_at") or now_iso),
            str(final_task.get("task_id") or final_task.get("run_id") or ""),
            SOURCE_INGESTION_WORKFLOW_TYPE,
            str(worker_id),
            clean_control,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise sqlite3.IntegrityError("Source-ingestion task ownership changed during finalize.")
    return load_source_ingestion_task_row(
        conn,
        str(final_task.get("task_id") or final_task.get("run_id") or ""),
    )


def persist_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    story_id: str | None = None,
    expected_worker_id: str = "",
    now: datetime | None = None,
) -> dict:
    """Create or save a task with ownership fencing in one write transaction.

    An empty result means that an existing worker owns the row or that the
    supplied worker lease is no longer authoritative.
    """
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    if not task_id:
        raise ValueError("Source-ingestion task ID cannot be empty.")
    current = now or _now()
    now_iso = _iso(current)
    conn.execute("BEGIN IMMEDIATE")
    identity_row = conn.execute(
        "SELECT workflow_type FROM workflow_runs WHERE run_id = ?",
        (task_id,),
    ).fetchone()
    if identity_row:
        workflow_type = str(_row_value(identity_row, "workflow_type", 0) or "")
        if workflow_type != SOURCE_INGESTION_WORKFLOW_TYPE:
            return {
                "persistence_conflict": "run_id",
                "conflicting_workflow_type": workflow_type,
            }
    row = _runtime_row(conn, task_id)
    clean_worker_id = str(expected_worker_id or "")

    if row is None:
        if clean_worker_id:
            return {}
        if _project_is_in_maintenance(conn):
            return {"persistence_conflict": "project_maintenance"}
        batch_conflict = ingestion_task_batch_conflict(
            conn,
            batch_id=str(task.get("batch_id") or ""),
            items=list(task.get("items") or []),
            expected_updated_at=str(task.get("batch_updated_at") or ""),
        )
        if batch_conflict:
            return {"persistence_conflict": batch_conflict}
        conflict_task_id = unfinished_batch_task_id(
            conn,
            batch_id=str(task.get("batch_id") or ""),
            exclude_task_id=task_id,
        )
        if conflict_task_id:
            return {
                "persistence_conflict": "unfinished_batch",
                "conflict_task_id": conflict_task_id,
            }
        _sync_source_ingestion_task_snapshot(conn, task=task, story_id=story_id)
        return load_source_ingestion_task_row(conn, task_id)

    owner = str(_row_value(row, "worker_id", 1) or "")
    if clean_worker_id:
        if not _worker_owns_live_running_row(row, worker_id=clean_worker_id, now_iso=now_iso):
            return {}
        requested_status = str(task.get("status") or "")
        if requested_status == "running":
            _sync_source_ingestion_task_snapshot(conn, task=task, story_id=story_id)
            return load_source_ingestion_task_row(conn, task_id)
        return _finalize_owned_source_ingestion_task_row(
            conn,
            task=task,
            worker_id=clean_worker_id,
            story_id=story_id,
            now_iso=now_iso,
            control_requested=str(_row_value(row, "control_requested", 4) or ""),
        )

    if owner:
        return {}
    if str(task.get("status") or "") == "queued" and _project_is_in_maintenance(conn):
        return {"persistence_conflict": "project_maintenance"}
    _sync_source_ingestion_task_snapshot(conn, task=task, story_id=story_id)
    return load_source_ingestion_task_row(conn, task_id)


def finalize_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    worker_id: str,
    story_id: str | None = None,
    now: datetime | None = None,
    acknowledged_control: str = "",
) -> dict:
    """Persist a worker terminal snapshot and clear its lease atomically."""
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    if not task_id:
        raise ValueError("Source-ingestion task ID cannot be empty.")
    clean_worker_id = str(worker_id or "").strip()
    if not clean_worker_id:
        raise ValueError("Source-ingestion worker ID cannot be empty.")
    current = now or _now()
    now_iso = _iso(current)
    conn.execute("BEGIN IMMEDIATE")
    row = _runtime_row(conn, task_id)
    if not _worker_owns_live_running_row(row, worker_id=clean_worker_id, now_iso=now_iso):
        return {}
    return _finalize_owned_source_ingestion_task_row(
        conn,
        task=task,
        worker_id=clean_worker_id,
        story_id=story_id,
        now_iso=now_iso,
        control_requested=str(_row_value(row, "control_requested", 4) or ""),
        acknowledged_control=str(acknowledged_control or ""),
    )


def sync_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    story_id: str | None = None,
) -> dict:
    """Compatibility entry point backed by the fenced persistence path."""
    return persist_source_ingestion_task_row(
        conn,
        task=task,
        story_id=story_id,
        expected_worker_id=str(task.get("worker_id") or ""),
    )


def load_source_ingestion_task_row(conn: sqlite3.Connection, task_id: str) -> dict:
    row = conn.execute(
        _task_select_sql("run_id = ? AND workflow_type = ?"),
        (str(task_id or ""), SOURCE_INGESTION_WORKFLOW_TYPE),
    ).fetchone()
    return _task_from_row(row)


def list_source_ingestion_task_rows(
    conn: sqlite3.Connection,
    *,
    statuses: list[str] | None = None,
    include_archived: bool = False,
) -> list[dict]:
    conditions = ["workflow_type = ?"]
    params: list[Any] = [SOURCE_INGESTION_WORKFLOW_TYPE]
    if not include_archived:
        conditions.append("archived_at IS NULL")
    if statuses:
        clean_statuses = [str(status) for status in statuses if str(status)]
        if clean_statuses:
            placeholders = ",".join("?" for _ in clean_statuses)
            conditions.append(f"status IN ({placeholders})")
            params.extend(clean_statuses)
    rows = conn.execute(
        _task_select_sql(" AND ".join(conditions)) + " ORDER BY updated_at DESC, created_at DESC, run_id DESC",
        tuple(params),
    ).fetchall()
    return [_task_from_row(row) for row in rows]
