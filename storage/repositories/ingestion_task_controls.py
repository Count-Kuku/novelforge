from __future__ import annotations

import sqlite3
from datetime import datetime

from .ingestion_batch_mutations import (
    UNFINISHED_STATUSES,
    ingestion_task_batch_conflict,
    unfinished_batch_task_id,
)
from .ingestion_tasks import (
    ARCHIVABLE_STATUSES,
    CONTROL_REQUESTS,
    SOURCE_INGESTION_WORKFLOW_TYPE,
    _json_loads_dict,
    _iso,
    _now,
    _project_is_in_maintenance,
    _row_value,
)


def load_source_ingestion_task_control_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str = "",
) -> dict:
    row = conn.execute(
        """
        SELECT status, worker_id, control_requested, lease_expires_at, heartbeat_at, archived_at
        FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ?
        """,
        (str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
    ).fetchone()
    if not row:
        return {}
    owner = str(_row_value(row, "worker_id", 1) or "")
    return {
        "status": str(_row_value(row, "status", 0) or ""),
        "worker_id": owner,
        "owned": bool(worker_id and owner == str(worker_id)),
        "control_requested": str(_row_value(row, "control_requested", 2) or ""),
        "lease_expires_at": str(_row_value(row, "lease_expires_at", 3) or ""),
        "heartbeat_at": str(_row_value(row, "heartbeat_at", 4) or ""),
        "archived_at": str(_row_value(row, "archived_at", 5) or ""),
    }


def request_source_ingestion_task_control_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    control: str,
    now: datetime | None = None,
) -> dict:
    clean_control = str(control or "")
    if clean_control not in CONTROL_REQUESTS:
        raise ValueError(f"Unsupported source-ingestion task control: {clean_control}")
    now_iso = _iso(now or _now())
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """
        SELECT status, worker_id, lease_expires_at
        FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ? AND archived_at IS NULL
        """,
        (str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
    ).fetchone()
    if not row:
        return {}
    status = str(_row_value(row, "status", 0) or "")
    worker_id = str(_row_value(row, "worker_id", 1) or "")
    lease_expires_at = str(_row_value(row, "lease_expires_at", 2) or "")
    worker_active = status == "running" and bool(worker_id) and bool(lease_expires_at) and lease_expires_at > now_iso

    if clean_control == "resume":
        if _project_is_in_maintenance(conn):
            raise ValueError("Project maintenance mode blocks task resume.")
        if status not in {"paused", "failed"}:
            raise ValueError(f"Task status cannot be resumed: {status}")
        next_status = "queued"
        requested = ""
        clear_worker = True
    elif status in {"completed", "cancelled"}:
        raise ValueError(f"Terminal task cannot accept {clean_control}: {status}")
    elif worker_active:
        next_status = "running"
        requested = clean_control
        clear_worker = False
    else:
        next_status = "paused" if clean_control == "pause" else "cancelled"
        requested = ""
        clear_worker = True

    conn.execute(
        """
        UPDATE workflow_runs
        SET status = ?, control_requested = ?, updated_at = ?,
            worker_id = CASE WHEN ? THEN NULL ELSE worker_id END,
            heartbeat_at = CASE WHEN ? THEN NULL ELSE heartbeat_at END,
            lease_expires_at = CASE WHEN ? THEN NULL ELSE lease_expires_at END
        WHERE run_id = ? AND workflow_type = ?
        """,
        (
            next_status,
            requested,
            now_iso,
            int(clear_worker),
            int(clear_worker),
            int(clear_worker),
            str(task_id),
            SOURCE_INGESTION_WORKFLOW_TYPE,
        ),
    )
    result = load_source_ingestion_task_control_row(conn, task_id=str(task_id))
    result["immediate"] = clear_worker
    return result


def release_source_ingestion_task_lease_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    status: str,
    now: datetime | None = None,
) -> bool:
    clean_worker_id = str(worker_id or "").strip()
    if not clean_worker_id:
        raise ValueError("Source-ingestion worker ID cannot be empty.")
    now_iso = _iso(now or _now())
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
            control_requested = '', updated_at = ?
        WHERE run_id = ? AND workflow_type = ? AND worker_id = ? AND status = ?
          AND archived_at IS NULL
          AND COALESCE(control_requested, '') = ''
          AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
        """,
        (
            now_iso,
            str(task_id),
            SOURCE_INGESTION_WORKFLOW_TYPE,
            clean_worker_id,
            str(status),
            now_iso,
        ),
    )
    return int(cursor.rowcount or 0) == 1


def settle_stale_source_ingestion_controls_row(
    conn: sqlite3.Connection,
    *,
    now: datetime | None = None,
) -> int:
    now_iso = _iso(now or _now())
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET status = CASE control_requested WHEN 'pause' THEN 'paused' ELSE 'cancelled' END,
            worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
            control_requested = '', updated_at = ?
        WHERE workflow_type = ? AND status = 'running' AND archived_at IS NULL
          AND control_requested IN ('pause', 'cancel')
          AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
        """,
        (now_iso, SOURCE_INGESTION_WORKFLOW_TYPE, now_iso),
    )
    return int(cursor.rowcount or 0)


def set_source_ingestion_task_archived_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    archived: bool,
    now: datetime | None = None,
) -> bool:
    now_iso = _iso(now or _now())
    if archived:
        cursor = conn.execute(
            """
            UPDATE workflow_runs
            SET archived_at = ?, updated_at = ?
            WHERE run_id = ? AND workflow_type = ? AND status IN (?, ?, ?, ?)
              AND worker_id IS NULL
            """,
            (
                now_iso,
                now_iso,
                str(task_id),
                SOURCE_INGESTION_WORKFLOW_TYPE,
                *sorted(ARCHIVABLE_STATUSES),
            ),
        )
    else:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT status, output_json
            FROM workflow_runs
            WHERE run_id = ? AND workflow_type = ? AND archived_at IS NOT NULL
            """,
            (str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
        ).fetchone()
        if not row:
            return False
        status = str(_row_value(row, "status", 0) or "")
        payload = _json_loads_dict(_row_value(row, "output_json", 1))
        if status in UNFINISHED_STATUSES:
            if ingestion_task_batch_conflict(
                conn,
                batch_id=str(payload.get("batch_id") or ""),
                items=list(payload.get("items") or []),
            ):
                return False
            conflict_task_id = unfinished_batch_task_id(
                conn,
                batch_id=str(payload.get("batch_id") or ""),
                exclude_task_id=str(task_id),
            )
            if conflict_task_id:
                return False
        cursor = conn.execute(
            """
            UPDATE workflow_runs
            SET archived_at = NULL, updated_at = ?
            WHERE run_id = ? AND workflow_type = ? AND archived_at IS NOT NULL
            """,
            (now_iso, str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
        )
    return int(cursor.rowcount or 0) == 1


def delete_archived_source_ingestion_task_row(conn: sqlite3.Connection, *, task_id: str) -> bool:
    cursor = conn.execute(
        """
        DELETE FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ? AND archived_at IS NOT NULL AND worker_id IS NULL
        """,
        (str(task_id), SOURCE_INGESTION_WORKFLOW_TYPE),
    )
    return int(cursor.rowcount or 0) == 1


def cleanup_archived_source_ingestion_task_rows(conn: sqlite3.Connection, *, before: datetime) -> int:
    cursor = conn.execute(
        """
        DELETE FROM workflow_runs
        WHERE workflow_type = ? AND archived_at IS NOT NULL AND archived_at < ? AND worker_id IS NULL
        """,
        (SOURCE_INGESTION_WORKFLOW_TYPE, _iso(before)),
    )
    return int(cursor.rowcount or 0)
