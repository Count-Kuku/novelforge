from __future__ import annotations

import json
import sqlite3
from typing import Any


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


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


def _story_id_or_none(conn: sqlite3.Connection, story_id: Any) -> str | None:
    clean_story_id = str(story_id or "").strip()
    if not clean_story_id:
        return None
    row = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (clean_story_id,),
    ).fetchone()
    return clean_story_id if row else None


def sync_workflow_run_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    payload: dict,
    story_id: str | None = None,
    artifact_asset_id: str | None = None,
) -> dict:
    clean_run_id = str(run_id or payload.get("run_id") or "").strip()
    if not clean_run_id:
        raise ValueError("Workflow run ID cannot be empty.")
    clean_story_id = _story_id_or_none(conn, story_id or payload.get("story_id"))
    workflow_type = str(payload.get("workflow_type") or "chapter_pipeline")
    if payload.get("halted"):
        status = "halted"
    elif payload.get("success") is True:
        status = "completed"
    elif payload.get("failed_steps"):
        status = "failed"
    else:
        status = str(payload.get("status") or payload.get("current_step") or "unknown")
    clean_artifact_asset_id = str(artifact_asset_id or "").strip() or None
    if clean_artifact_asset_id:
        asset_row = conn.execute(
            "SELECT asset_id FROM asset_files WHERE asset_id = ?",
            (clean_artifact_asset_id,),
        ).fetchone()
        if not asset_row:
            clean_artifact_asset_id = None
    conn.execute(
        """
        INSERT INTO workflow_runs (
            run_id, story_id, workflow_type, status, parent_run_id,
            input_json, output_json, error_json, started_at, finished_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(run_id) DO UPDATE SET
            story_id = excluded.story_id,
            workflow_type = excluded.workflow_type,
            status = excluded.status,
            parent_run_id = excluded.parent_run_id,
            input_json = excluded.input_json,
            output_json = excluded.output_json,
            error_json = excluded.error_json,
            started_at = excluded.started_at,
            finished_at = excluded.finished_at
        """,
        (
            clean_run_id,
            clean_story_id,
            workflow_type,
            status,
            str(payload.get("parent_run_id") or "").strip() or None,
            _json_dumps({
                "project_name": payload.get("project_name", ""),
                "chapter_no": payload.get("chapter_no"),
                "user_requirement": payload.get("user_requirement", ""),
                "word_count": payload.get("word_count", ""),
            }),
            _json_dumps(payload),
            _json_dumps(payload.get("errors", [])),
            str(payload.get("started_at") or ""),
            str(payload.get("finished_at") or ""),
        ),
    )
    steps = payload.get("steps", {})
    if not isinstance(steps, dict):
        steps = {}
    active_step_ids: list[str] = []
    for order, (step_name, raw_step) in enumerate(steps.items(), start=1):
        step = dict(raw_step) if isinstance(raw_step, dict) else {}
        clean_step_name = str(step.get("step_name") or step_name)
        step_id = f"{clean_run_id}:{clean_step_name}"
        active_step_ids.append(step_id)
        conn.execute(
            """
            INSERT INTO workflow_steps (
                step_id, run_id, step_name, step_order, status,
                input_json, output_json, error_json, artifact_asset_id,
                started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, '{}', ?, ?, ?, '', '')
            ON CONFLICT(step_id) DO UPDATE SET
                step_name = excluded.step_name,
                step_order = excluded.step_order,
                status = excluded.status,
                output_json = excluded.output_json,
                error_json = excluded.error_json,
                artifact_asset_id = excluded.artifact_asset_id
            """,
            (
                step_id,
                clean_run_id,
                clean_step_name,
                order,
                str(step.get("status") or "unknown"),
                _json_dumps(step),
                _json_dumps({"error": step.get("error", ""), "warnings": step.get("warnings", [])}),
                clean_artifact_asset_id,
            ),
        )
    if active_step_ids:
        placeholders = ",".join("?" for _ in active_step_ids)
        conn.execute(
            f"DELETE FROM workflow_steps WHERE run_id = ? AND step_id NOT IN ({placeholders})",
            (clean_run_id, *active_step_ids),
        )
    else:
        conn.execute("DELETE FROM workflow_steps WHERE run_id = ?", (clean_run_id,))
    return payload


def load_workflow_run_snapshot(conn: sqlite3.Connection, run_id: str, story_id: str | None = None) -> dict:
    clean_run_id = str(run_id or "").strip()
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        row = conn.execute(
            """
            SELECT output_json
            FROM workflow_runs
            WHERE run_id = ? AND story_id = ?
            """,
            (clean_run_id, clean_story_id),
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT output_json
                FROM workflow_runs
                WHERE run_id = ?
                """,
                (clean_run_id,),
            ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT output_json
            FROM workflow_runs
            WHERE run_id = ?
            """,
            (clean_run_id,),
        ).fetchone()
    if not row:
        return {}
    return _json_loads_dict(row["output_json"] if isinstance(row, sqlite3.Row) else row[0])


def list_workflow_run_ids(
    conn: sqlite3.Connection,
    *,
    story_id: str | None = None,
    chapter_no: int | None = None,
) -> list[str]:
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        rows = conn.execute(
            """
            SELECT run_id, output_json, created_at
            FROM workflow_runs
            WHERE story_id = ?
            ORDER BY created_at DESC, run_id DESC
            """,
            (clean_story_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT run_id, output_json, created_at
            FROM workflow_runs
            ORDER BY created_at DESC, run_id DESC
            """
        ).fetchall()
    run_ids: list[str] = []
    for row in rows:
        run_id = row["run_id"] if isinstance(row, sqlite3.Row) else row[0]
        if chapter_no is not None:
            payload = _json_loads_dict(row["output_json"] if isinstance(row, sqlite3.Row) else row[1])
            try:
                payload_chapter_no = int(payload.get("chapter_no"))
            except (TypeError, ValueError):
                continue
            if payload_chapter_no != chapter_no:
                continue
        run_ids.append(str(run_id))
    return run_ids


def list_workflow_run_summaries(
    conn: sqlite3.Connection,
    *,
    story_id: str | None = None,
    chapter_no: int | None = None,
) -> list[dict]:
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        rows = conn.execute(
            """
            SELECT run_id, story_id, workflow_type, status, output_json, started_at, finished_at, created_at
            FROM workflow_runs
            WHERE story_id = ?
            ORDER BY created_at DESC, run_id DESC
            """,
            (clean_story_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT run_id, story_id, workflow_type, status, output_json, started_at, finished_at, created_at
            FROM workflow_runs
            ORDER BY created_at DESC, run_id DESC
            """
        ).fetchall()
    summaries: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["output_json"] if isinstance(row, sqlite3.Row) else row[4])
        payload_chapter_no = payload.get("chapter_no")
        try:
            normalized_chapter_no = int(payload_chapter_no)
        except (TypeError, ValueError):
            normalized_chapter_no = None
        if chapter_no is not None and normalized_chapter_no != chapter_no:
            continue
        summaries.append({
            "run_id": str(row["run_id"] if isinstance(row, sqlite3.Row) else row[0]),
            "story_id": row["story_id"] if isinstance(row, sqlite3.Row) else row[1],
            "workflow_type": row["workflow_type"] if isinstance(row, sqlite3.Row) else row[2],
            "status": row["status"] if isinstance(row, sqlite3.Row) else row[3],
            "chapter_no": normalized_chapter_no,
            "updated_at": row["created_at"] if isinstance(row, sqlite3.Row) else row[7],
            "started_at": row["started_at"] if isinstance(row, sqlite3.Row) else row[5],
            "finished_at": row["finished_at"] if isinstance(row, sqlite3.Row) else row[6],
            "payload": payload,
        })
    return summaries


def delete_workflow_run_snapshot(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    story_id: str | None = None,
) -> int:
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        return 0
    clean_story_id = str(story_id or "").strip()
    if clean_story_id:
        cursor = conn.execute(
            "DELETE FROM workflow_runs WHERE run_id = ? AND story_id = ?",
            (clean_run_id, clean_story_id),
        )
        if cursor.rowcount:
            return int(cursor.rowcount)
    cursor = conn.execute("DELETE FROM workflow_runs WHERE run_id = ?", (clean_run_id,))
    return int(cursor.rowcount or 0)
