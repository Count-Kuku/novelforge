"""Atomic authority checks for long-reference batch mutations."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .sources import mark_long_reference_batch_deleted, sync_long_reference_batch


SOURCE_INGESTION_WORKFLOW_TYPE = "source_ingestion"
UNFINISHED_STATUSES = {"queued", "running", "paused", "failed", "completed_with_errors"}


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


def unfinished_batch_task_id(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    exclude_task_id: str = "",
) -> str:
    """Return an unfinished batch owner while the caller holds a write lock."""
    clean_batch_id = str(batch_id or "").strip()
    if not clean_batch_id:
        return ""
    placeholders = ",".join("?" for _ in UNFINISHED_STATUSES)
    params: list[Any] = [SOURCE_INGESTION_WORKFLOW_TYPE, *sorted(UNFINISHED_STATUSES)]
    exclude_sql = ""
    if exclude_task_id:
        exclude_sql = " AND run_id <> ?"
        params.append(str(exclude_task_id))
    rows = conn.execute(
        f"""
        SELECT run_id, output_json
        FROM workflow_runs
        WHERE workflow_type = ? AND archived_at IS NULL
          AND status IN ({placeholders}){exclude_sql}
        """,
        tuple(params),
    ).fetchall()
    for row in rows:
        payload = _json_loads_dict(row["output_json"] if isinstance(row, sqlite3.Row) else row[1])
        if str(payload.get("batch_id") or "").strip() == clean_batch_id:
            return str(row["run_id"] if isinstance(row, sqlite3.Row) else row[0])
    return ""


def ingestion_task_batch_conflict(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    items: list[dict],
    expected_updated_at: str = "",
) -> str:
    """Validate a task's immutable segment selection against the DB batch."""
    clean_batch_id = str(batch_id or "").strip()
    row = conn.execute(
        """
        SELECT metadata_json
        FROM source_documents
        WHERE source_id = ? AND deleted_at IS NULL
        LIMIT 1
        """,
        (f"long_batch_{clean_batch_id}",),
    ).fetchone()
    if row is None:
        return "batch_missing"
    payload = _json_loads_dict(row["metadata_json"] if isinstance(row, sqlite3.Row) else row[0])
    clean_expected_updated_at = str(expected_updated_at or "").strip()
    if (
        clean_expected_updated_at
        and str(payload.get("updated_at") or "").strip() != clean_expected_updated_at
    ):
        return "batch_changed"
    segments = payload.get("segments", []) if isinstance(payload.get("segments", []), list) else []
    segment_ids = {
        str(segment.get("segment_id") or "")
        for segment in segments
        if isinstance(segment, dict) and str(segment.get("segment_id") or "")
    }
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            return "batch_changed"
        segment_id = str(item.get("segment_id") or "")
        if segment_id:
            if segment_id not in segment_ids:
                return "batch_changed"
            continue
        try:
            segment_index = int(item.get("segment_index", -1))
        except (TypeError, ValueError):
            segment_index = -1
        if not 0 <= segment_index < len(segments):
            return "batch_changed"
    return ""


def _project_is_in_maintenance(conn: sqlite3.Connection) -> bool:
    return conn.execute(
        "SELECT 1 FROM project_meta WHERE maintenance_mode = 1 LIMIT 1"
    ).fetchone() is not None


def _require_live_worker_authority(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    batch_id: str,
) -> None:
    row = conn.execute(
        """
        SELECT status, worker_id, lease_expires_at
        FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ? AND archived_at IS NULL
        """,
        (task_id, SOURCE_INGESTION_WORKFLOW_TYPE),
    ).fetchone()
    if row is None:
        raise ValueError(f"资料任务“{task_id}”不存在或已归档，不能保存批次“{batch_id}”。")
    status = str(row["status"] if isinstance(row, sqlite3.Row) else row[0])
    owner = str((row["worker_id"] if isinstance(row, sqlite3.Row) else row[1]) or "")
    if status in {"failed", "completed_with_errors"}:
        if owner or worker_id:
            raise ValueError(
                f"资料任务“{task_id}”的失败状态只能由无 worker 的重试流程更新批次“{batch_id}”。"
            )
        return
    if status != "running":
        raise ValueError(
            f"资料任务“{task_id}”当前状态为“{status}”，不能保存批次“{batch_id}”。"
        )
    lease_text = str((row["lease_expires_at"] if isinstance(row, sqlite3.Row) else row[2]) or "")
    try:
        lease_expires_at = datetime.fromisoformat(lease_text.replace("Z", "+00:00"))
        if lease_expires_at.tzinfo is None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timezone.utc)
        lease_is_live = lease_expires_at > datetime.now(timezone.utc)
    except ValueError:
        lease_is_live = False
    if not worker_id or str(worker_id) != owner or not lease_is_live:
        raise ValueError(
            f"资料任务“{task_id}”的当前 worker 不持有有效租约，不能保存批次“{batch_id}”。"
        )


def _require_batch_mutation_authority(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    task_id: str = "",
    worker_id: str = "",
    operation: str,
) -> None:
    clean_batch_id = str(batch_id or "").strip()
    clean_task_id = str(task_id or "").strip()
    occupying_task_id = unfinished_batch_task_id(conn, batch_id=clean_batch_id)
    if not occupying_task_id:
        if clean_task_id:
            raise ValueError(
                f"资料任务“{clean_task_id}”不是批次“{clean_batch_id}”当前有效的占用任务，不能{operation}。"
            )
        return
    if not clean_task_id:
        raise ValueError(
            f"资料批次“{clean_batch_id}”正由未完成任务“{occupying_task_id}”占用，"
            f"不能{operation}；请先处理或归档该任务。"
        )
    if clean_task_id != occupying_task_id:
        raise ValueError(
            f"资料任务“{clean_task_id}”无权{operation}批次“{clean_batch_id}”；"
            f"当前占用任务为“{occupying_task_id}”。"
        )
    if operation == "保存":
        _require_live_worker_authority(
            conn,
            task_id=clean_task_id,
            worker_id=str(worker_id or ""),
            batch_id=clean_batch_id,
        )


def persist_long_reference_batch_row(
    conn: sqlite3.Connection,
    *,
    batch: dict,
    task_id: str = "",
    worker_id: str = "",
) -> dict:
    """Save a batch only when no task owns it or the owning task is supplied."""
    payload = dict(batch or {})
    batch_id = str(payload.get("batch_id") or "").strip()
    if not batch_id:
        raise ValueError("资料批次 ID 不能为空。")
    conn.execute("BEGIN IMMEDIATE")
    if _project_is_in_maintenance(conn) and not (str(task_id or "").strip() and str(worker_id or "").strip()):
        raise ValueError("项目正在重命名或删除，暂时不能保存资料批次。")
    _require_batch_mutation_authority(
        conn,
        batch_id=batch_id,
        task_id=task_id,
        worker_id=worker_id,
        operation="保存",
    )
    return sync_long_reference_batch(conn, payload)


def delete_long_reference_batch_row(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
) -> bool:
    """Delete a batch only when no unfinished, unarchived task owns it."""
    clean_batch_id = str(batch_id or "").strip()
    if not clean_batch_id:
        raise ValueError("资料批次 ID 不能为空。")
    conn.execute("BEGIN IMMEDIATE")
    if _project_is_in_maintenance(conn):
        raise ValueError("项目正在重命名或删除，暂时不能删除资料批次。")
    _require_batch_mutation_authority(
        conn,
        batch_id=clean_batch_id,
        operation="删除",
    )
    return bool(mark_long_reference_batch_deleted(conn, batch_id=clean_batch_id))
