"""Append-only LLM usage ledger and aggregate queries."""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable


EVENT_COLUMNS = (
    "event_id",
    "provider_request_id",
    "occurred_at",
    "project_name",
    "story_id",
    "workflow_run_id",
    "task_id",
    "operation_id",
    "operation",
    "agent_role",
    "profile_id",
    "provider",
    "endpoint_type",
    "requested_model",
    "reported_model",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "embedding_tokens",
    "total_tokens",
    "cost_microusd",
    "provider_cost_microusd",
    "calculated_cost_microusd",
    "cost_source",
    "usage_status",
    "price_snapshot_json",
    "metadata_json",
)


def _json_text(value: object) -> str:
    if isinstance(value, str):
        try:
            json.loads(value)
        except (TypeError, ValueError):
            return json.dumps({}, ensure_ascii=False)
        return value
    return json.dumps(value if isinstance(value, (dict, list)) else {}, ensure_ascii=False)


def _event_value(event: dict, column: str):
    if column in {"price_snapshot_json", "metadata_json"}:
        source_key = column.removesuffix("_json")
        return _json_text(event.get(column, event.get(source_key, {})))
    if column in {
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
        "embedding_tokens",
        "total_tokens",
    }:
        return max(int(event.get(column) or 0), 0)
    if column in {"cost_microusd", "provider_cost_microusd", "calculated_cost_microusd"}:
        value = event.get(column)
        return None if value is None else max(int(value), 0)
    if column == "provider_request_id":
        return str(event.get(column) or "").strip() or None
    return str(event.get(column) or "")


def insert_llm_usage_event_row(conn: sqlite3.Connection, event: dict) -> bool:
    placeholders = ", ".join("?" for _ in EVENT_COLUMNS)
    columns = ", ".join(EVENT_COLUMNS)
    cursor = conn.execute(
        f"INSERT OR IGNORE INTO llm_usage_events ({columns}) VALUES ({placeholders})",
        tuple(_event_value(event, column) for column in EVENT_COLUMNS),
    )
    return cursor.rowcount > 0


def _filters(
    *,
    project_name: str | None = None,
    story_id: str | None = None,
    task_id: str | None = None,
    operation_id: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    for column, value in (
        ("project_name", project_name),
        ("story_id", story_id),
        ("task_id", task_id),
        ("operation_id", operation_id),
    ):
        if value is None:
            continue
        clauses.append(f"{column} = ?")
        params.append(str(value))
    if start_at:
        clauses.append("occurred_at >= ?")
        params.append(str(start_at))
    if end_at:
        clauses.append("occurred_at < ?")
        params.append(str(end_at))
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


SUMMARY_SELECT = """
    COUNT(*) AS request_count,
    COALESCE(SUM(input_tokens), 0) AS input_tokens,
    COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
    COALESCE(SUM(cache_write_tokens), 0) AS cache_write_tokens,
    COALESCE(SUM(output_tokens), 0) AS output_tokens,
    COALESCE(SUM(reasoning_tokens), 0) AS reasoning_tokens,
    COALESCE(SUM(embedding_tokens), 0) AS embedding_tokens,
    COALESCE(SUM(total_tokens), 0) AS total_tokens,
    COALESCE(SUM(cost_microusd), 0) AS cost_microusd,
    SUM(CASE WHEN cost_microusd IS NOT NULL THEN 1 ELSE 0 END) AS priced_request_count,
    SUM(CASE WHEN cost_microusd IS NULL THEN 1 ELSE 0 END) AS unpriced_request_count,
    SUM(CASE WHEN usage_status = 'estimated' THEN 1 ELSE 0 END) AS estimated_request_count,
    SUM(CASE WHEN cost_source = 'provider_reported' THEN 1 ELSE 0 END) AS provider_cost_count,
    SUM(CASE WHEN cost_source = 'tokens_only' THEN 1 ELSE 0 END) AS tokens_only_request_count
"""


def summarize_llm_usage_rows(conn: sqlite3.Connection, **filters) -> dict:
    where, params = _filters(**filters)
    row = conn.execute(f"SELECT {SUMMARY_SELECT} FROM llm_usage_events{where}", params).fetchone()
    return dict(row) if row is not None else {}


def list_daily_llm_usage_rows(
    conn: sqlite3.Connection,
    *,
    utc_offset_minutes: int = 480,
    **filters,
) -> list[dict]:
    where, params = _filters(**filters)
    offset = max(min(int(utc_offset_minutes), 14 * 60), -12 * 60)
    modifier = f"{offset:+d} minutes"
    rows = conn.execute(
        f"""
        SELECT date(occurred_at, ?) AS usage_date, {SUMMARY_SELECT}
        FROM llm_usage_events
        {where}
        GROUP BY usage_date
        ORDER BY usage_date ASC
        """,
        [modifier, *params],
    ).fetchall()
    return [dict(row) for row in rows]


_BREAKDOWN_COLUMNS = {
    "model": "CASE WHEN reported_model <> '' THEN reported_model ELSE requested_model END",
    "operation": "operation",
    "agent_role": "CASE WHEN agent_role <> '' THEN agent_role ELSE '未标记' END",
    "provider": "provider",
}


def list_llm_usage_breakdown_rows(
    conn: sqlite3.Connection,
    *,
    dimension: str,
    limit: int = 20,
    **filters,
) -> list[dict]:
    expression = _BREAKDOWN_COLUMNS.get(str(dimension))
    if expression is None:
        raise ValueError(f"Unsupported usage breakdown dimension: {dimension}")
    where, params = _filters(**filters)
    rows = conn.execute(
        f"""
        SELECT {expression} AS bucket, {SUMMARY_SELECT}
        FROM llm_usage_events
        {where}
        GROUP BY bucket
        ORDER BY total_tokens DESC, request_count DESC
        LIMIT ?
        """,
        [*params, max(min(int(limit), 100), 1)],
    ).fetchall()
    return [dict(row) for row in rows]


def list_recent_llm_usage_event_rows(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
    **filters,
) -> list[dict]:
    where, params = _filters(**filters)
    rows = conn.execute(
        f"""
        SELECT {', '.join(EVENT_COLUMNS)}
        FROM llm_usage_events
        {where}
        ORDER BY occurred_at DESC, event_id DESC
        LIMIT ?
        """,
        [*params, max(min(int(limit), 5000), 1)],
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for column in ("price_snapshot_json", "metadata_json"):
            try:
                item[column.removesuffix("_json")] = json.loads(item.pop(column) or "{}")
            except (TypeError, ValueError):
                item[column.removesuffix("_json")] = {}
        result.append(item)
    return result


def delete_llm_usage_event_rows(
    conn: sqlite3.Connection,
    *,
    event_ids: Iterable[str] | None = None,
    project_name: str | None = None,
    before: str | None = None,
) -> int:
    clauses: list[str] = []
    params: list[object] = []
    clean_ids = [str(item) for item in (event_ids or []) if str(item)]
    if clean_ids:
        clauses.append(f"event_id IN ({', '.join('?' for _ in clean_ids)})")
        params.extend(clean_ids)
    if project_name is not None:
        clauses.append("project_name = ?")
        params.append(str(project_name))
    if before:
        clauses.append("occurred_at < ?")
        params.append(str(before))
    if not clauses:
        raise ValueError("Refusing to delete usage events without an explicit scope.")
    cursor = conn.execute(
        "DELETE FROM llm_usage_events WHERE " + " AND ".join(clauses),
        params,
    )
    return max(int(cursor.rowcount), 0)


def rename_llm_usage_project_rows(
    conn: sqlite3.Connection,
    old_project_name: str,
    new_project_name: str,
) -> int:
    old_name = str(old_project_name or "").strip()
    new_name = str(new_project_name or "").strip()
    if not old_name or not new_name:
        raise ValueError("Both old and new project names are required.")
    if old_name == new_name:
        return 0
    cursor = conn.execute(
        "UPDATE llm_usage_events SET project_name = ? WHERE project_name = ?",
        (new_name, old_name),
    )
    return max(int(cursor.rowcount), 0)
