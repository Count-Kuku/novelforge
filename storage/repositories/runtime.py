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


def _float_or_default(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def sync_auto_review_policy(conn: sqlite3.Connection, policy: dict) -> dict:
    payload = dict(policy or {})
    conn.execute(
        """
        INSERT INTO auto_review_policy (policy_id, policy_json, created_at, updated_at)
        VALUES ('default', ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        ON CONFLICT(policy_id) DO UPDATE SET
            policy_json = excluded.policy_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (_json_dumps(payload),),
    )
    return payload


def load_auto_review_policy_row(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        """
        SELECT policy_json
        FROM auto_review_policy
        WHERE policy_id = 'default'
        """
    ).fetchone()
    if not row:
        return {}
    return _json_loads_dict(row["policy_json"] if isinstance(row, sqlite3.Row) else row[0])


def sync_auto_review_runs(conn: sqlite3.Connection, runs: list[dict]) -> list[dict]:
    normalized = [dict(item) for item in runs if isinstance(item, dict)]
    active_ids: list[str] = []
    for item in normalized:
        run_id = str(item.get("run_id") or "").strip()
        if not run_id:
            continue
        active_ids.append(run_id)
        conn.execute(
            """
            INSERT INTO auto_review_runs (run_id, run_type, status, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
            ON CONFLICT(run_id) DO UPDATE SET
                run_type = excluded.run_type,
                status = excluded.status,
                payload_json = excluded.payload_json,
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            """,
            (
                run_id,
                str(item.get("run_type") or item.get("type") or "auto_review"),
                str(item.get("status") or "active"),
                _json_dumps(item),
                str(item.get("created_at") or ""),
            ),
        )
    return normalized


def load_auto_review_run_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT run_id, run_type, status, payload_json, created_at, updated_at
        FROM auto_review_runs
        ORDER BY created_at, run_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["payload_json"] if isinstance(row, sqlite3.Row) else row[3])
        run_id = row["run_id"] if isinstance(row, sqlite3.Row) else row[0]
        payload.setdefault("run_id", run_id)
        payload.setdefault("run_type", row["run_type"] if isinstance(row, sqlite3.Row) else row[1])
        payload.setdefault("status", row["status"] if isinstance(row, sqlite3.Row) else row[2])
        payload.setdefault("created_at", row["created_at"] if isinstance(row, sqlite3.Row) else row[4])
        items.append(payload)
    return items


def sync_retrieval_eval_cases(conn: sqlite3.Connection, cases: list[dict]) -> list[dict]:
    normalized = [dict(item) for item in cases if isinstance(item, dict)]
    active_ids: list[str] = []
    for item in normalized:
        case_id = str(item.get("case_id") or "").strip()
        if not case_id:
            continue
        active_ids.append(case_id)
        conn.execute(
            """
            INSERT INTO retrieval_eval_cases (
                case_id, story_id, name, query, task_type, expected_json, enabled,
                created_at, updated_at, deleted_at
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL)
            ON CONFLICT(case_id) DO UPDATE SET
                name = excluded.name,
                query = excluded.query,
                task_type = excluded.task_type,
                expected_json = excluded.expected_json,
                enabled = excluded.enabled,
                updated_at = excluded.updated_at,
                deleted_at = NULL
            """,
            (
                case_id,
                str(item.get("name") or item.get("query") or "未命名评测用例"),
                str(item.get("query") or ""),
                str(item.get("retrieval_profile") or item.get("task_type") or ""),
                _json_dumps(item),
                0 if str(item.get("status") or "active") == "archived" else 1,
                str(item.get("created_at") or ""),
                str(item.get("updated_at") or ""),
            ),
        )
    if active_ids:
        placeholders = ",".join("?" for _ in active_ids)
        conn.execute(
            f"""
            UPDATE retrieval_eval_cases
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE case_id NOT IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(active_ids),
        )
    else:
        conn.execute(
            """
            UPDATE retrieval_eval_cases
            SET deleted_at = COALESCE(deleted_at, strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
                updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            WHERE deleted_at IS NULL
            """
        )
    return normalized


def load_retrieval_eval_case_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT case_id, story_id, name, query, task_type, expected_json, enabled,
               created_at, updated_at
        FROM retrieval_eval_cases
        WHERE deleted_at IS NULL
        ORDER BY created_at, case_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["expected_json"] if isinstance(row, sqlite3.Row) else row[5])
        case_id = row["case_id"] if isinstance(row, sqlite3.Row) else row[0]
        payload.setdefault("case_id", case_id)
        payload.setdefault("name", row["name"] if isinstance(row, sqlite3.Row) else row[2])
        payload.setdefault("query", row["query"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("retrieval_profile", row["task_type"] if isinstance(row, sqlite3.Row) else row[4])
        if not (row["enabled"] if isinstance(row, sqlite3.Row) else row[6]):
            payload.setdefault("status", "archived")
        payload.setdefault("created_at", row["created_at"] if isinstance(row, sqlite3.Row) else row[7])
        payload.setdefault("updated_at", row["updated_at"] if isinstance(row, sqlite3.Row) else row[8])
        items.append(payload)
    return items


def sync_retrieval_eval_run(conn: sqlite3.Connection, run: dict) -> dict:
    payload = dict(run or {})
    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("Retrieval evaluation run ID cannot be empty.")
    conn.execute(
        """
        INSERT INTO retrieval_eval_runs (run_id, case_id, story_id, status, result_json, created_at)
        VALUES (?, ?, NULL, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            case_id = excluded.case_id,
            status = excluded.status,
            result_json = excluded.result_json
        """,
        (
            run_id,
            str(payload.get("case_id") or "").strip() or None,
            str(payload.get("status") or "completed"),
            _json_dumps(payload),
            str(payload.get("created_at") or ""),
        ),
    )
    return payload


def load_retrieval_eval_run_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT run_id, case_id, status, result_json, created_at
        FROM retrieval_eval_runs
        ORDER BY created_at, run_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["result_json"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("run_id", row["run_id"] if isinstance(row, sqlite3.Row) else row[0])
        case_id = row["case_id"] if isinstance(row, sqlite3.Row) else row[1]
        if case_id is not None:
            payload.setdefault("case_id", case_id)
        payload.setdefault("status", row["status"] if isinstance(row, sqlite3.Row) else row[2])
        payload.setdefault("created_at", row["created_at"] if isinstance(row, sqlite3.Row) else row[4])
        items.append(payload)
    return items


def append_retrieval_feedback_row(conn: sqlite3.Connection, feedback: dict) -> dict:
    payload = dict(feedback or {})
    feedback_id = str(payload.get("feedback_id") or "").strip()
    if not feedback_id:
        raise ValueError("Retrieval feedback ID cannot be empty.")
    chunk_id = str(payload.get("chunk_id") or "").strip() or None
    if chunk_id:
        row = conn.execute(
            "SELECT chunk_id FROM retrieval_chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        if not row:
            chunk_id = None
    conn.execute(
        """
        INSERT INTO retrieval_feedback (
            feedback_id, chunk_id, story_id, task_type, feedback_type, reason,
            weight, created_at, payload_json
        )
        VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(feedback_id) DO UPDATE SET
            chunk_id = excluded.chunk_id,
            task_type = excluded.task_type,
            feedback_type = excluded.feedback_type,
            reason = excluded.reason,
            weight = excluded.weight,
            payload_json = excluded.payload_json
        """,
            (
                feedback_id,
            chunk_id,
            str(payload.get("retrieval_profile") or payload.get("task_type") or "").strip() or None,
            str(payload.get("rating") or payload.get("feedback_type") or "").strip(),
            str(payload.get("note") or payload.get("reason") or "").strip(),
            _float_or_default(payload.get("weight"), 0.0),
            str(payload.get("created_at") or ""),
            _json_dumps(payload),
        ),
    )
    return payload


def load_retrieval_feedback_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT feedback_id, chunk_id, task_type, feedback_type, reason, weight,
               created_at, payload_json
        FROM retrieval_feedback
        ORDER BY created_at, feedback_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["payload_json"] if isinstance(row, sqlite3.Row) else row[7])
        payload.setdefault("feedback_id", row["feedback_id"] if isinstance(row, sqlite3.Row) else row[0])
        chunk_id = row["chunk_id"] if isinstance(row, sqlite3.Row) else row[1]
        if chunk_id is not None:
            payload.setdefault("chunk_id", chunk_id)
        payload.setdefault("retrieval_profile", row["task_type"] if isinstance(row, sqlite3.Row) else row[2])
        payload.setdefault("rating", row["feedback_type"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("note", row["reason"] if isinstance(row, sqlite3.Row) else row[4])
        payload.setdefault("weight", row["weight"] if isinstance(row, sqlite3.Row) else row[5])
        payload.setdefault("created_at", row["created_at"] if isinstance(row, sqlite3.Row) else row[6])
        items.append(payload)
    return items


def sync_conflict_resolution(conn: sqlite3.Connection, resolution: dict) -> dict:
    payload = dict(resolution or {})
    resolution_id = str(payload.get("conflict_id") or payload.get("resolution_id") or "").strip()
    if not resolution_id:
        raise ValueError("Conflict resolution ID cannot be empty.")
    conn.execute(
        """
        INSERT INTO retrieval_conflict_resolutions (
            resolution_id, story_id, conflict_key, preferred_scope, preferred_source_id,
            decision, rationale, payload_json, created_at, updated_at
        )
        VALUES (
            ?, NULL, ?, ?, NULL, ?, ?, ?,
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        )
        ON CONFLICT(resolution_id) DO UPDATE SET
            conflict_key = excluded.conflict_key,
            preferred_scope = excluded.preferred_scope,
            decision = excluded.decision,
            rationale = excluded.rationale,
            payload_json = excluded.payload_json,
            updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
        """,
        (
            resolution_id,
            str(payload.get("conflict_key") or payload.get("conflict_id") or resolution_id),
            str(payload.get("preferred_scope") or payload.get("scope") or "").strip() or None,
            str(payload.get("decision") or payload.get("chosen_resolution") or "manual"),
            str(payload.get("rationale") or payload.get("note") or ""),
            _json_dumps(payload),
        ),
    )
    return payload


def load_conflict_resolution_rows(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT resolution_id, conflict_key, preferred_scope, decision, rationale,
               payload_json, created_at, updated_at
        FROM retrieval_conflict_resolutions
        ORDER BY updated_at, resolution_id
        """
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        payload = _json_loads_dict(row["payload_json"] if isinstance(row, sqlite3.Row) else row[5])
        resolution_id = row["resolution_id"] if isinstance(row, sqlite3.Row) else row[0]
        payload.setdefault("conflict_id", resolution_id)
        payload.setdefault("resolution_id", resolution_id)
        payload.setdefault("conflict_key", row["conflict_key"] if isinstance(row, sqlite3.Row) else row[1])
        payload.setdefault("decision", row["decision"] if isinstance(row, sqlite3.Row) else row[3])
        payload.setdefault("note", row["rationale"] if isinstance(row, sqlite3.Row) else row[4])
        payload.setdefault("updated_at", row["updated_at"] if isinstance(row, sqlite3.Row) else row[7])
        items.append(payload)
    return items
