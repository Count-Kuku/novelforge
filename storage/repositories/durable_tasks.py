"""Generic leased task operations backed by workflow_runs/workflow_steps."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from .workflows import sync_workflow_run_snapshot


CLAIMABLE_STATUSES = {"queued", "running"}
ARCHIVABLE_STATUSES = {"paused", "failed", "completed_with_errors", "completed", "cancelled"}
FINAL_STATUSES = {"paused", "failed", "completed_with_errors", "completed", "cancelled"}
CONTROL_REQUESTS = {"pause", "cancel", "resume"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _row_value(row: sqlite3.Row | tuple, key: str, index: int):
    return row[key] if isinstance(row, sqlite3.Row) else row[index]


def _json_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or ""))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _task_select_sql(where_sql: str) -> str:
    return f"""
        SELECT run_id, story_id, workflow_type, status, output_json,
               updated_at, worker_id, lease_expires_at, heartbeat_at,
               control_requested, priority, archived_at
        FROM workflow_runs
        WHERE {where_sql}
    """


def _task_from_row(row: sqlite3.Row | tuple | None) -> dict:
    if row is None:
        return {}
    payload = _json_dict(_row_value(row, "output_json", 4))
    payload.update(
        {
            "task_id": str(_row_value(row, "run_id", 0)),
            "run_id": str(_row_value(row, "run_id", 0)),
            "story_id": str(_row_value(row, "story_id", 1) or payload.get("story_id") or ""),
            "workflow_type": str(_row_value(row, "workflow_type", 2)),
            "status": str(_row_value(row, "status", 3)),
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


def _project_in_maintenance(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM project_meta WHERE maintenance_mode = 1 LIMIT 1").fetchone() is not None


def _runtime_row(conn: sqlite3.Connection, task_id: str, workflow_type: str):
    return conn.execute(
        """
        SELECT status, worker_id, lease_expires_at, archived_at, control_requested
        FROM workflow_runs WHERE run_id = ? AND workflow_type = ?
        """,
        (task_id, workflow_type),
    ).fetchone()


def _owns_live_row(row, worker_id: str, now_iso: str) -> bool:
    return bool(
        row
        and worker_id
        and str(_row_value(row, "status", 0) or "") == "running"
        and str(_row_value(row, "worker_id", 1) or "") == worker_id
        and str(_row_value(row, "lease_expires_at", 2) or "") > now_iso
        and not _row_value(row, "archived_at", 3)
    )


def _sync_task(conn: sqlite3.Connection, task: dict, workflow_type: str) -> None:
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    payload = {**task, "task_id": task_id, "run_id": task_id, "workflow_type": workflow_type}
    sync_workflow_run_snapshot(
        conn,
        run_id=task_id,
        payload=payload,
        story_id=str(task.get("story_id") or "") or None,
    )
    estimate = dict(task.get("estimate") or {})
    conn.execute(
        """
        UPDATE workflow_runs
        SET updated_at = ?, priority = ?, estimated_input_tokens = ?,
            estimated_output_tokens = ?, estimated_embedding_tokens = ?, estimated_cost_usd = ?
        WHERE run_id = ? AND workflow_type = ?
        """,
        (
            str(task.get("updated_at") or _iso(_now())),
            int(task.get("priority") or 0),
            int(estimate.get("estimated_input_tokens") or 0),
            int(estimate.get("estimated_output_tokens") or 0),
            int(estimate.get("estimated_embedding_tokens") or 0),
            float(estimate.get("estimated_cost_usd") or 0.0),
            task_id,
            workflow_type,
        ),
    )


def load_durable_task_row(conn: sqlite3.Connection, *, task_id: str, workflow_type: str) -> dict:
    row = conn.execute(
        _task_select_sql("run_id = ? AND workflow_type = ?"),
        (str(task_id), str(workflow_type)),
    ).fetchone()
    return _task_from_row(row)


def list_durable_task_rows(
    conn: sqlite3.Connection,
    *,
    workflow_type: str,
    statuses: list[str] | None = None,
    include_archived: bool = False,
) -> list[dict]:
    conditions = ["workflow_type = ?"]
    params: list[Any] = [str(workflow_type)]
    if not include_archived:
        conditions.append("archived_at IS NULL")
    clean_statuses = [str(item) for item in (statuses or []) if str(item)]
    if clean_statuses:
        conditions.append(f"status IN ({','.join('?' for _ in clean_statuses)})")
        params.extend(clean_statuses)
    rows = conn.execute(
        _task_select_sql(" AND ".join(conditions))
        + " ORDER BY updated_at DESC, created_at DESC, run_id DESC",
        tuple(params),
    ).fetchall()
    return [_task_from_row(row) for row in rows]


def persist_durable_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    workflow_type: str,
    expected_worker_id: str = "",
    now: datetime | None = None,
) -> dict:
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    clean_type = str(workflow_type or "").strip()
    if not task_id or not clean_type:
        raise ValueError("Durable task ID and workflow type are required.")
    now_iso = _iso(now or _now())
    conn.execute("BEGIN IMMEDIATE")
    identity = conn.execute("SELECT workflow_type FROM workflow_runs WHERE run_id = ?", (task_id,)).fetchone()
    if identity and str(_row_value(identity, "workflow_type", 0) or "") != clean_type:
        return {"persistence_conflict": "run_id"}
    row = _runtime_row(conn, task_id, clean_type)
    worker_id = str(expected_worker_id or "")
    if row is None:
        if worker_id:
            return {}
        if _project_in_maintenance(conn):
            return {"persistence_conflict": "project_maintenance"}
        _sync_task(conn, task, clean_type)
        return load_durable_task_row(conn, task_id=task_id, workflow_type=clean_type)
    owner = str(_row_value(row, "worker_id", 1) or "")
    if worker_id:
        if not _owns_live_row(row, worker_id, now_iso) or str(task.get("status") or "") != "running":
            return {}
        _sync_task(conn, task, clean_type)
        return load_durable_task_row(conn, task_id=task_id, workflow_type=clean_type)
    if owner:
        return {}
    if str(task.get("status") or "") == "queued" and _project_in_maintenance(conn):
        return {"persistence_conflict": "project_maintenance"}
    _sync_task(conn, task, clean_type)
    return load_durable_task_row(conn, task_id=task_id, workflow_type=clean_type)


def finalize_durable_task_row(
    conn: sqlite3.Connection,
    *,
    task: dict,
    workflow_type: str,
    worker_id: str,
    acknowledged_control: str = "",
    now: datetime | None = None,
) -> dict:
    task_id = str(task.get("task_id") or task.get("run_id") or "").strip()
    clean_type = str(workflow_type or "").strip()
    clean_worker = str(worker_id or "").strip()
    final_status = str(task.get("status") or "")
    if not task_id or not clean_worker or final_status not in FINAL_STATUSES:
        raise ValueError("Durable task finalization arguments are invalid.")
    now_iso = _iso(now or _now())
    conn.execute("BEGIN IMMEDIATE")
    row = _runtime_row(conn, task_id, clean_type)
    if not _owns_live_row(row, clean_worker, now_iso):
        return {}
    requested = str(_row_value(row, "control_requested", 4) or "")
    matching = {"paused": "pause", "cancelled": "cancel"}.get(final_status, "")
    completion_ack = final_status in {"completed", "completed_with_errors"} and acknowledged_control == requested
    if requested and matching != requested and not completion_ack:
        return load_durable_task_row(conn, task_id=task_id, workflow_type=clean_type)
    final_task = {
        **task,
        "worker_id": "",
        "heartbeat_at": "",
        "lease_expires_at": "",
        "control_requested": "",
        "updated_at": str(task.get("updated_at") or now_iso),
    }
    _sync_task(conn, final_task, clean_type)
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET worker_id = NULL, heartbeat_at = NULL, lease_expires_at = NULL,
            control_requested = '', updated_at = ?
        WHERE run_id = ? AND workflow_type = ? AND worker_id = ?
          AND COALESCE(control_requested, '') = ?
        """,
        (final_task["updated_at"], task_id, clean_type, clean_worker, requested),
    )
    if int(cursor.rowcount or 0) != 1:
        raise sqlite3.IntegrityError("Durable task ownership changed during finalize.")
    return load_durable_task_row(conn, task_id=task_id, workflow_type=clean_type)


def claim_durable_task_row(
    conn: sqlite3.Connection,
    *,
    workflow_type: str,
    worker_id: str,
    lease_seconds: int,
    task_id: str = "",
    now: datetime | None = None,
) -> dict:
    clean_type = str(workflow_type or "").strip()
    clean_worker = str(worker_id or "").strip()
    if not clean_type or not clean_worker:
        raise ValueError("Durable task workflow type and worker ID are required.")
    current = now or _now()
    now_iso = _iso(current)
    lease_iso = _iso(current + timedelta(seconds=max(int(lease_seconds), 1)))
    conn.execute("BEGIN IMMEDIATE")
    conditions = [
        "workflow_type = ?",
        "archived_at IS NULL",
        "COALESCE(control_requested, '') = ''",
        "NOT EXISTS (SELECT 1 FROM project_meta WHERE maintenance_mode = 1)",
        "(status = 'queued' OR (status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at <= ?)))",
    ]
    params: list[Any] = [clean_type, now_iso]
    if task_id:
        conditions.append("run_id = ?")
        params.append(str(task_id))
    row = conn.execute(
        "SELECT run_id FROM workflow_runs WHERE " + " AND ".join(conditions)
        + " ORDER BY priority DESC, created_at ASC, run_id ASC LIMIT 1",
        tuple(params),
    ).fetchone()
    if not row:
        return {}
    claimed_id = str(_row_value(row, "run_id", 0))
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET status = 'running', worker_id = ?, heartbeat_at = ?, lease_expires_at = ?,
            updated_at = ?, control_requested = ''
        WHERE run_id = ? AND workflow_type = ? AND archived_at IS NULL
          AND NOT EXISTS (SELECT 1 FROM project_meta WHERE maintenance_mode = 1)
          AND COALESCE(control_requested, '') = ''
          AND (status = 'queued' OR (status = 'running' AND (lease_expires_at IS NULL OR lease_expires_at <= ?)))
        """,
        (clean_worker, now_iso, lease_iso, now_iso, claimed_id, clean_type, now_iso),
    )
    if int(cursor.rowcount or 0) != 1:
        return {}
    return load_durable_task_row(conn, task_id=claimed_id, workflow_type=clean_type)


def heartbeat_durable_task_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    workflow_type: str,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    current = now or _now()
    now_iso = _iso(current)
    lease_iso = _iso(current + timedelta(seconds=max(int(lease_seconds), 1)))
    cursor = conn.execute(
        """
        UPDATE workflow_runs SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
        WHERE run_id = ? AND workflow_type = ? AND status = 'running'
          AND worker_id = ? AND archived_at IS NULL
          AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
        """,
        (now_iso, lease_iso, now_iso, str(task_id), str(workflow_type), str(worker_id), now_iso),
    )
    return int(cursor.rowcount or 0) == 1


def load_durable_task_control_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    workflow_type: str,
    worker_id: str = "",
) -> dict:
    row = conn.execute(
        """
        SELECT status, worker_id, control_requested, lease_expires_at, heartbeat_at, archived_at
        FROM workflow_runs WHERE run_id = ? AND workflow_type = ?
        """,
        (str(task_id), str(workflow_type)),
    ).fetchone()
    if not row:
        return {}
    now_iso = _iso(_now())
    owner = str(_row_value(row, "worker_id", 1) or "")
    status = str(_row_value(row, "status", 0) or "")
    lease_expires_at = str(_row_value(row, "lease_expires_at", 3) or "")
    archived_at = str(_row_value(row, "archived_at", 5) or "")
    return {
        "status": status,
        "worker_id": owner,
        "owned": bool(
            worker_id
            and owner == str(worker_id)
            and status == "running"
            and lease_expires_at > now_iso
            and not archived_at
        ),
        "control_requested": str(_row_value(row, "control_requested", 2) or ""),
        "lease_expires_at": lease_expires_at,
        "heartbeat_at": str(_row_value(row, "heartbeat_at", 4) or ""),
        "archived_at": archived_at,
    }


def request_durable_task_control_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    workflow_type: str,
    control: str,
    now: datetime | None = None,
) -> dict:
    clean_control = str(control or "")
    if clean_control not in CONTROL_REQUESTS:
        raise ValueError(f"Unsupported durable task control: {clean_control}")
    now_iso = _iso(now or _now())
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute(
        """
        SELECT status, worker_id, lease_expires_at FROM workflow_runs
        WHERE run_id = ? AND workflow_type = ? AND archived_at IS NULL
        """,
        (str(task_id), str(workflow_type)),
    ).fetchone()
    if not row:
        return {}
    status = str(_row_value(row, "status", 0) or "")
    owner = str(_row_value(row, "worker_id", 1) or "")
    lease = str(_row_value(row, "lease_expires_at", 2) or "")
    active = status == "running" and bool(owner) and lease > now_iso
    if clean_control == "resume":
        if _project_in_maintenance(conn):
            raise ValueError("Project maintenance mode blocks task resume.")
        if status not in {"paused", "failed", "completed_with_errors"}:
            raise ValueError(f"Task status cannot be resumed: {status}")
        next_status, requested, clear_worker = "queued", "", True
    elif status in {"completed", "cancelled"}:
        raise ValueError(f"Terminal task cannot accept {clean_control}: {status}")
    elif active:
        next_status, requested, clear_worker = "running", clean_control, False
    else:
        next_status = "paused" if clean_control == "pause" else "cancelled"
        requested, clear_worker = "", True
    conn.execute(
        """
        UPDATE workflow_runs
        SET status = ?, control_requested = ?, updated_at = ?,
            worker_id = CASE WHEN ? THEN NULL ELSE worker_id END,
            heartbeat_at = CASE WHEN ? THEN NULL ELSE heartbeat_at END,
            lease_expires_at = CASE WHEN ? THEN NULL ELSE lease_expires_at END
        WHERE run_id = ? AND workflow_type = ?
        """,
        (next_status, requested, now_iso, int(clear_worker), int(clear_worker), int(clear_worker), str(task_id), str(workflow_type)),
    )
    result = load_durable_task_control_row(conn, task_id=str(task_id), workflow_type=str(workflow_type))
    result["immediate"] = clear_worker
    return result


def settle_stale_durable_task_controls_row(
    conn: sqlite3.Connection,
    *,
    workflow_type: str,
    now: datetime | None = None,
) -> int:
    now_iso = _iso(now or _now())
    rows = conn.execute(
        """
        SELECT run_id, output_json, control_requested
        FROM workflow_runs
        WHERE workflow_type = ? AND status = 'running' AND archived_at IS NULL
          AND control_requested IN ('pause', 'cancel')
          AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
        """,
        (str(workflow_type), now_iso),
    ).fetchall()
    settled = 0
    for row in rows:
        run_id = str(_row_value(row, "run_id", 0))
        payload = _json_dict(_row_value(row, "output_json", 1))
        control = str(_row_value(row, "control_requested", 2) or "")
        status = "paused" if control == "pause" else "cancelled"
        payload.update(
            {
                "status": status,
                "worker_id": "",
                "heartbeat_at": "",
                "lease_expires_at": "",
                "control_requested": "",
                "updated_at": now_iso,
            }
        )
        if status == "paused":
            payload["paused_at"] = now_iso
        else:
            payload["cancelled_at"] = now_iso
            payload["finished_at"] = now_iso
        steps = payload.get("steps", {}) if isinstance(payload.get("steps"), dict) else {}
        for step in steps.values():
            if isinstance(step, dict) and step.get("status") == "running":
                step["status"] = "pending"
                step["updated_at"] = now_iso
        cursor = conn.execute(
            """
            UPDATE workflow_runs
            SET status = ?, output_json = ?, worker_id = NULL, heartbeat_at = NULL,
                lease_expires_at = NULL, control_requested = '', updated_at = ?,
                finished_at = CASE WHEN ? = 'cancelled' THEN ? ELSE finished_at END
            WHERE run_id = ? AND workflow_type = ? AND status = 'running'
              AND control_requested = ?
              AND (lease_expires_at IS NULL OR lease_expires_at <= ?)
            """,
            (
                status,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                now_iso,
                status,
                now_iso,
                run_id,
                str(workflow_type),
                control,
                now_iso,
            ),
        )
        if int(cursor.rowcount or 0) == 1:
            conn.execute(
                """
                UPDATE workflow_steps SET status = 'pending'
                WHERE run_id = ? AND status = 'running'
                """,
                (run_id,),
            )
            settled += 1
    return settled


def set_durable_task_archived_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    workflow_type: str,
    archived: bool,
    now: datetime | None = None,
) -> bool:
    now_iso = _iso(now or _now())
    if archived:
        placeholders = ",".join("?" for _ in ARCHIVABLE_STATUSES)
        cursor = conn.execute(
            f"""
            UPDATE workflow_runs SET archived_at = ?, updated_at = ?
            WHERE run_id = ? AND workflow_type = ? AND status IN ({placeholders}) AND worker_id IS NULL
            """,
            (now_iso, now_iso, str(task_id), str(workflow_type), *sorted(ARCHIVABLE_STATUSES)),
        )
    else:
        cursor = conn.execute(
            """
            UPDATE workflow_runs SET archived_at = NULL, updated_at = ?
            WHERE run_id = ? AND workflow_type = ? AND archived_at IS NOT NULL AND worker_id IS NULL
            """,
            (now_iso, str(task_id), str(workflow_type)),
        )
    return int(cursor.rowcount or 0) == 1


def delete_archived_durable_task_row(conn: sqlite3.Connection, *, task_id: str, workflow_type: str) -> bool:
    cursor = conn.execute(
        "DELETE FROM workflow_runs WHERE run_id = ? AND workflow_type = ? AND archived_at IS NOT NULL AND worker_id IS NULL",
        (str(task_id), str(workflow_type)),
    )
    return int(cursor.rowcount or 0) == 1
