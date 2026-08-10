"""Streamlit views for token and cost observability."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone

import streamlit as st

from novelforge.core.cost_currency import (
    convert_cost,
    cost_display_preferences,
    normalize_cost_currency,
)
from novelforge.services.llm_usage import (
    list_daily_llm_usage,
    list_llm_usage_breakdown,
    list_recent_llm_usage_events,
    local_utc_offset_minutes,
    summarize_llm_usage,
    summarize_local_period,
)
from novelforge.services.memory import load_llm_settings


DIMENSION_LABELS = {
    "model": "模型",
    "provider": "供应商",
    "operation": "操作",
    "agent_role": "Agent 角色",
}
ENDPOINT_LABELS = {"chat": "对话", "embedding": "Embedding"}
USAGE_STATUS_LABELS = {"exact": "精确", "estimated": "估算"}
COST_SOURCE_LABELS = {
    "provider_reported": "供应商返回",
    "configured_rates": "配置价格估算",
    "tokens_only": "仅 Token",
    "unpriced": "未配置价格",
    "local_zero": "本地模型",
}


def format_token_count(value: int | float | None) -> str:
    count = max(int(value or 0), 0)
    if count >= 1_000_000:
        return f"{count / 1_000_000:.2f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def format_cost_usd(value: int | float | None) -> str:
    amount = max(float(value or 0), 0.0)
    if amount == 0:
        return "$0.000000"
    if amount < 0.01:
        return f"${amount:.6f}"
    return f"${amount:.4f}"


def format_cost_cny(value: int | float | None) -> str:
    amount = max(float(value or 0), 0.0)
    if amount == 0:
        return "¥0.000000"
    if amount < 0.01:
        return f"¥{amount:.6f}"
    return f"¥{amount:.4f}"


def _load_cost_preferences() -> dict[str, object]:
    try:
        return cost_display_preferences(load_llm_settings())
    except Exception:
        return cost_display_preferences({})


def _display_cost_usd(value: int | float | None, preferences: dict) -> str:
    display_currency = normalize_cost_currency(
        preferences.get("display_currency"), default="CNY"
    )
    if display_currency == "USD":
        return format_cost_usd(value)
    converted = convert_cost(
        float(value or 0),
        source_currency="USD",
        target_currency="CNY",
        usd_to_cny_rate=preferences.get("usd_to_cny_rate"),
    )
    return format_cost_cny(converted)


def format_usage_cost(summary: dict, preferences: dict | None = None) -> str:
    display = cost_display_preferences(preferences or {})
    requests = int(summary.get("request_count") or 0)
    if requests <= 0:
        return "—"
    priced = int(summary.get("priced_request_count") or 0)
    unpriced = int(summary.get("unpriced_request_count") or 0)
    if priced <= 0:
        if int(summary.get("tokens_only_request_count") or 0) == requests:
            return "仅记录 Token"
        return "费用未配置"
    value = _display_cost_usd(summary.get("cost_usd"), display)
    provider_count = int(summary.get("provider_cost_count") or 0)
    prefix = (
        ""
        if provider_count == priced and display["display_currency"] == "USD"
        else "≈"
    )
    suffix = f" + {unpriced} 次未计价" if unpriced else ""
    return f"{prefix}{value}{suffix}"


def usage_summary_text(summary: dict, preferences: dict | None = None) -> str:
    if not summary.get("has_usage"):
        return "本次没有产生模型调用"
    estimated = int(summary.get("estimated_request_count") or 0)
    estimate_note = f" · 含 {estimated} 次 Token 估算" if estimated else ""
    return (
        f"{format_token_count(summary.get('total_tokens'))} Token · "
        f"{format_usage_cost(summary, preferences)} · {int(summary.get('request_count') or 0)} 次调用{estimate_note}"
    )


def render_operation_usage_summary(operation_id: str, *, container=None) -> None:
    if not operation_id:
        return
    host = container or st
    try:
        summary = summarize_llm_usage(operation_id=operation_id)
    except Exception:
        return
    if summary.get("has_usage"):
        host.caption(
            f"本次用量：{usage_summary_text(summary, _load_cost_preferences())}"
        )


def render_sidebar_usage_summary(project_name: str, story_id: str) -> None:
    try:
        today = summarize_local_period("today", project_name=project_name, story_id=story_id)
        month = summarize_local_period("month", project_name=project_name, story_id=story_id)
    except Exception:
        return
    preferences = _load_cost_preferences()
    st.sidebar.caption(
        f"今日用量：{format_token_count(today.get('total_tokens'))} Token · {format_usage_cost(today, preferences)}"
    )
    st.sidebar.caption(
        f"本月用量：{format_token_count(month.get('total_tokens'))} Token · {format_usage_cost(month, preferences)}"
    )


def _period_start(period_days: int | None) -> str | None:
    if period_days is None:
        return None
    local_now = datetime.now().astimezone()
    start_local = (local_now - timedelta(days=max(period_days - 1, 0))).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )
    return start_local.astimezone(timezone.utc).isoformat()


def _filters(project_name: str | None, story_id: str | None, period_days: int | None) -> dict:
    result: dict[str, str] = {}
    if project_name is not None:
        result["project_name"] = project_name
    if story_id is not None:
        result["story_id"] = story_id
    start_at = _period_start(period_days)
    if start_at:
        result["start_at"] = start_at
    return result


def _cost_columns(value: int | float | None, preferences: dict) -> dict[str, float]:
    usd = max(float(value or 0), 0.0)
    cny = convert_cost(
        usd,
        source_currency="USD",
        target_currency="CNY",
        usd_to_cny_rate=preferences.get("usd_to_cny_rate"),
    )
    columns = {
        "费用（CNY）": round(cny, 6),
        "费用（USD）": round(usd, 6),
    }
    if preferences.get("display_currency") == "USD":
        return {"费用（USD）": columns["费用（USD）"], "费用（CNY）": columns["费用（CNY）"]}
    return columns


def _daily_table(rows: list[dict], preferences: dict) -> list[dict]:
    return [
        {
            "日期": row.get("usage_date", ""),
            "调用次数": int(row.get("request_count") or 0),
            "输入 Token": int(row.get("input_tokens") or 0),
            "缓存输入 Token": int(row.get("cached_input_tokens") or 0),
            "输出 Token": int(row.get("output_tokens") or 0),
            "Embedding Token": int(row.get("embedding_tokens") or 0),
            "总 Token": int(row.get("total_tokens") or 0),
            **_cost_columns(row.get("cost_usd"), preferences),
            "未计价调用": int(row.get("unpriced_request_count") or 0),
        }
        for row in rows
    ]


def _breakdown_table(rows: list[dict], dimension: str, preferences: dict) -> list[dict]:
    return [
        {
            DIMENSION_LABELS[dimension]: row.get("bucket", "未标记"),
            "调用次数": int(row.get("request_count") or 0),
            "总 Token": int(row.get("total_tokens") or 0),
            **_cost_columns(row.get("cost_usd"), preferences),
            "未计价调用": int(row.get("unpriced_request_count") or 0),
        }
        for row in rows
    ]


def _recent_table(rows: list[dict], preferences: dict) -> list[dict]:
    result = []
    for row in rows:
        cost = row.get("cost_usd")
        row_preferences = dict(preferences)
        price_snapshot = row.get("price_snapshot")
        if isinstance(price_snapshot, dict) and price_snapshot.get("usd_to_cny_rate"):
            row_preferences["usd_to_cny_rate"] = price_snapshot["usd_to_cny_rate"]
        cost_columns = (
            {"费用（CNY）": "—", "费用（USD）": "—"}
            if cost is None
            else {
                key: f"{value:.6f}"
                for key, value in _cost_columns(cost, row_preferences).items()
            }
        )
        result.append(
            {
                "时间": str(row.get("occurred_at") or "").replace("T", " ")[:19],
                "项目": row.get("project_name") or "—",
                "故事": row.get("story_id") or "—",
                "Agent": row.get("agent_role") or "未标记",
                "操作": row.get("operation") or "未标记",
                "供应商": row.get("provider") or "未知",
                "模型": row.get("reported_model") or row.get("requested_model") or "未知",
                "类型": ENDPOINT_LABELS.get(row.get("endpoint_type"), row.get("endpoint_type") or "未知"),
                "Token": int(row.get("total_tokens") or 0),
                **cost_columns,
                "Token 状态": USAGE_STATUS_LABELS.get(row.get("usage_status"), row.get("usage_status") or "未知"),
                "费用来源": COST_SOURCE_LABELS.get(row.get("cost_source"), row.get("cost_source") or "未知"),
            }
        )
    return result


def _csv_bytes(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def render_usage_dashboard(
    *,
    project_name: str | None = None,
    story_id: str | None = None,
    key_prefix: str = "llm_usage",
) -> None:
    period_label = st.selectbox(
        "统计范围",
        options=["最近 7 天", "最近 30 天", "最近 90 天", "全部记录"],
        index=1,
        key=f"{key_prefix}_period",
    )
    period_days = {"最近 7 天": 7, "最近 30 天": 30, "最近 90 天": 90}.get(period_label)
    filters = _filters(project_name, story_id, period_days)
    summary = summarize_llm_usage(**filters)
    preferences = _load_cost_preferences()

    metrics = st.columns(4)
    metrics[0].metric("总 Token", format_token_count(summary.get("total_tokens")))
    metrics[1].metric("模型调用", int(summary.get("request_count") or 0))
    metrics[2].metric("费用", format_usage_cost(summary, preferences))
    metrics[3].metric("未计价调用", int(summary.get("unpriced_request_count") or 0))
    st.caption(
        "人民币为默认主显示；“≈”表示按 Token 单价或当前换算系数估算。"
        "底层历史账本保留 USD，最近调用优先使用事件换算快照；按日和分组聚合中的人民币按当前系数换算。"
    )

    daily = list_daily_llm_usage(
        utc_offset_minutes=local_utc_offset_minutes(),
        **filters,
    )
    daily_table = _daily_table(daily, preferences)
    if daily_table:
        chart_rows = [{"日期": row["日期"], "Token": row["总 Token"]} for row in daily_table]
        st.line_chart(chart_rows, x="日期", y="Token")
        with st.expander("按日期明细", expanded=False):
            st.dataframe(daily_table, use_container_width=True, hide_index=True)
    else:
        st.info("当前范围内还没有模型用量记录。")

    dimension = st.selectbox(
        "拆分维度",
        options=list(DIMENSION_LABELS),
        format_func=lambda value: DIMENSION_LABELS[value],
        key=f"{key_prefix}_dimension",
    )
    breakdown = _breakdown_table(
        list_llm_usage_breakdown(dimension=dimension, **filters),
        dimension,
        preferences,
    )
    if breakdown:
        st.dataframe(breakdown, use_container_width=True, hide_index=True)

    with st.expander("最近调用与导出", expanded=False):
        recent = _recent_table(
            list_recent_llm_usage_events(limit=200, **filters), preferences
        )
        if recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
            st.download_button(
                "导出当前明细 CSV",
                data=_csv_bytes(recent),
                file_name=f"novelforge-llm-usage-{datetime.now().date().isoformat()}.csv",
                mime="text/csv",
                key=f"{key_prefix}_download",
            )
        else:
            st.caption("暂无可导出的调用记录。")
