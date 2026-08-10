"""Application service for the global LLM usage ledger."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

from storage import open_global_db
from storage.repositories import (
    delete_llm_usage_event_rows,
    insert_llm_usage_event_row,
    list_llm_usage_calibration_rows,
    list_daily_llm_usage_rows,
    list_llm_usage_breakdown_rows,
    list_recent_llm_usage_event_rows,
    rename_llm_usage_project_rows,
    summarize_llm_usage_rows,
)


def _decorate_summary(summary: dict | None) -> dict:
    payload = dict(summary or {})
    for key in (
        "request_count",
        "input_tokens",
        "cached_input_tokens",
        "cache_write_tokens",
        "output_tokens",
        "reasoning_tokens",
        "embedding_tokens",
        "total_tokens",
        "cost_microusd",
        "priced_request_count",
        "unpriced_request_count",
        "estimated_request_count",
        "provider_cost_count",
        "tokens_only_request_count",
    ):
        payload[key] = int(payload.get(key) or 0)
    payload["cost_usd"] = payload["cost_microusd"] / 1_000_000
    payload["cost_complete"] = payload["request_count"] > 0 and payload["unpriced_request_count"] == 0
    payload["has_usage"] = payload["request_count"] > 0
    return payload


def record_llm_usage_event(event: dict) -> bool:
    with open_global_db() as conn:
        inserted = insert_llm_usage_event_row(conn, event)
        conn.commit()
        return inserted


def summarize_llm_usage(**filters) -> dict:
    with open_global_db() as conn:
        return _decorate_summary(summarize_llm_usage_rows(conn, **filters))


def list_daily_llm_usage(**filters) -> list[dict]:
    with open_global_db() as conn:
        rows = list_daily_llm_usage_rows(conn, **filters)
    result = []
    for row in rows:
        decorated = _decorate_summary(row)
        decorated["usage_date"] = str(row.get("usage_date") or "")
        result.append(decorated)
    return result


def list_llm_usage_breakdown(*, dimension: str, **filters) -> list[dict]:
    with open_global_db() as conn:
        rows = list_llm_usage_breakdown_rows(conn, dimension=dimension, **filters)
    result = []
    for row in rows:
        decorated = _decorate_summary(row)
        decorated["bucket"] = str(row.get("bucket") or "未标记")
        result.append(decorated)
    return result


def list_recent_llm_usage_events(**filters) -> list[dict]:
    with open_global_db() as conn:
        rows = list_recent_llm_usage_event_rows(conn, **filters)
    for row in rows:
        value = row.get("cost_microusd")
        row["cost_usd"] = None if value is None else int(value) / 1_000_000
    return rows


def _nearest_rank(values: list[int], percentile: float) -> int:
    clean = sorted(max(int(value or 0), 0) for value in values if int(value or 0) > 0)
    if not clean:
        return 0
    rank = max(1, math.ceil(len(clean) * percentile))
    return clean[min(rank - 1, len(clean) - 1)]


def get_llm_usage_calibration(*, limit: int = 500, **filters) -> dict:
    """Return P50/P90 per-call usage for one model/operation/agent cohort."""

    with open_global_db() as conn:
        rows = list_llm_usage_calibration_rows(conn, limit=limit, **filters)
    result = {"sample_count": len(rows)}
    for column in ("input_tokens", "output_tokens", "embedding_tokens", "total_tokens"):
        values = [int(row.get(column) or 0) for row in rows]
        prefix = column.removesuffix("_tokens")
        result[f"{prefix}_p50"] = _nearest_rank(values, 0.50)
        result[f"{prefix}_p90"] = _nearest_rank(values, 0.90)
    return result


def delete_llm_usage_history(
    *,
    project_name: str | None = None,
    before: str | None = None,
    event_ids: list[str] | None = None,
) -> int:
    with open_global_db() as conn:
        count = delete_llm_usage_event_rows(
            conn,
            project_name=project_name,
            before=before,
            event_ids=event_ids,
        )
        conn.commit()
        return count


def rename_llm_usage_project(old_project_name: str, new_project_name: str) -> int:
    with open_global_db() as conn:
        count = rename_llm_usage_project_rows(conn, old_project_name, new_project_name)
        conn.commit()
        return count


def local_period_bounds(period: str, *, now: datetime | None = None) -> tuple[str, str]:
    local_now = now.astimezone() if now is not None else datetime.now().astimezone()
    if period == "today":
        start_local = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "month":
        start_local = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unsupported usage period: {period}")
    end_local = local_now + timedelta(microseconds=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )


def summarize_local_period(period: str, **filters) -> dict:
    start_at, end_at = local_period_bounds(period)
    return summarize_llm_usage(start_at=start_at, end_at=end_at, **filters)


def local_utc_offset_minutes() -> int:
    offset = datetime.now().astimezone().utcoffset() or timedelta(0)
    return int(offset.total_seconds() // 60)
