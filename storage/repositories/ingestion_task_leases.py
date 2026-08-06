from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from .ingestion_tasks import (
    SOURCE_INGESTION_WORKFLOW_TYPE,
    _iso,
    _now,
    _row_value,
    load_source_ingestion_task_row,
)


def _claim_source_ingestion_task(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int,
    task_id: str = "",
    now: datetime | None = None,
) -> dict:
    clean_worker_id = str(worker_id or "").strip()
    if not clean_worker_id:
        raise ValueError("Source-ingestion worker ID cannot be empty.")
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
    params: list[object] = [SOURCE_INGESTION_WORKFLOW_TYPE, now_iso]
    if task_id:
        conditions.append("run_id = ?")
        params.append(str(task_id))
    row = conn.execute(
        """
        SELECT run_id
        FROM workflow_runs
        WHERE """ + " AND ".join(conditions) + " ORDER BY priority DESC, created_at ASC, run_id ASC LIMIT 1",
        tuple(params),
    ).fetchone()
    if not row:
        return {}
    claimed_task_id = str(_row_value(row, "run_id", 0))
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
        (
            clean_worker_id,
            now_iso,
            lease_iso,
            now_iso,
            claimed_task_id,
            SOURCE_INGESTION_WORKFLOW_TYPE,
            now_iso,
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        return {}
    return load_source_ingestion_task_row(conn, claimed_task_id)


def claim_next_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> dict:
    return _claim_source_ingestion_task(
        conn,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
    )


def claim_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> dict:
    return _claim_source_ingestion_task(
        conn,
        task_id=task_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        now=now,
    )


def heartbeat_source_ingestion_task_row(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    clean_worker_id = str(worker_id or "").strip()
    if not clean_worker_id:
        raise ValueError("Source-ingestion worker ID cannot be empty.")
    current = now or _now()
    now_iso = _iso(current)
    lease_iso = _iso(current + timedelta(seconds=max(int(lease_seconds), 1)))
    cursor = conn.execute(
        """
        UPDATE workflow_runs
        SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
        WHERE run_id = ? AND workflow_type = ? AND status = 'running'
          AND worker_id = ? AND archived_at IS NULL
          AND lease_expires_at IS NOT NULL AND lease_expires_at > ?
        """,
        (
            now_iso,
            lease_iso,
            now_iso,
            str(task_id),
            SOURCE_INGESTION_WORKFLOW_TYPE,
            clean_worker_id,
            now_iso,
        ),
    )
    return int(cursor.rowcount or 0) == 1
