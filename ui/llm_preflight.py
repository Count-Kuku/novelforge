"""Reusable Streamlit rendering for execution preflight estimates."""
from __future__ import annotations

import streamlit as st

from novelforge.core.cost_currency import (
    convert_cost_range,
    normalize_cost_currency,
    normalize_usd_to_cny_rate,
)

def format_tokens(value: object) -> str:
    number = int(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)


def _range_value(value: object, fallback: object = 0) -> dict[str, int]:
    if isinstance(value, dict):
        expected = int(value.get("expected") or 0)
        return {
            "low": int(value.get("low", expected) or 0),
            "expected": expected,
            "high": int(value.get("high", expected) or 0),
        }
    expected = int(fallback if value is None else value or 0)
    return {"low": expected, "expected": expected, "high": expected}


def _token_metric(column, label: str, value: dict) -> None:
    column.metric(
        label,
        format_tokens(value["expected"]),
        help=f"预计范围：{format_tokens(value['low'])}～{format_tokens(value['high'])}",
    )


def _cost_text(cost_range: dict | None, currency: str = "CNY") -> str:
    if not isinstance(cost_range, dict):
        return "未计价"
    amount = max(float(cost_range.get("expected") or 0), 0.0)
    normalized_currency = normalize_cost_currency(currency, default="CNY")
    symbol = "¥" if normalized_currency == "CNY" else "$"
    if amount == 0:
        return f"{symbol}0.000000"
    if amount < 0.01:
        return f"{symbol}{amount:.6f}"
    return f"{symbol}{amount:.4f}"


def _cost_ranges(payload: dict) -> tuple[str, dict | None, str, dict | None]:
    display_currency = normalize_cost_currency(
        payload.get("display_currency"), default="CNY"
    )
    secondary_currency = "USD" if display_currency == "CNY" else "CNY"
    rate = normalize_usd_to_cny_rate(payload.get("usd_to_cny_rate"))
    usd_range = payload.get("cost_range_usd")
    cny_range = payload.get("cost_range_cny")
    if not isinstance(cny_range, dict) and isinstance(usd_range, dict):
        cny_range = convert_cost_range(
            usd_range,
            source_currency="USD",
            target_currency="CNY",
            usd_to_cny_rate=rate,
        )
    if not isinstance(usd_range, dict) and isinstance(cny_range, dict):
        usd_range = convert_cost_range(
            cny_range,
            source_currency="CNY",
            target_currency="USD",
            usd_to_cny_rate=rate,
        )
    primary = cny_range if display_currency == "CNY" else usd_range
    secondary = usd_range if display_currency == "CNY" else cny_range
    return display_currency, primary, secondary_currency, secondary


def render_preflight_estimate(
    estimate: dict,
    *,
    expanded: bool = False,
    confirmation_key: str | None = None,
    leading_metrics: dict[str, object] | None = None,
) -> bool:
    """Render an estimate and return whether a required budget check is approved."""

    payload = dict(estimate or {})
    if not payload or not bool(payload.get("enabled", True)):
        return True
    input_range = _range_value(
        payload.get("input_tokens"), payload.get("estimated_input_tokens")
    )
    output_range = _range_value(
        payload.get("output_tokens"), payload.get("estimated_output_tokens")
    )
    embedding_range = _range_value(
        payload.get("embedding_tokens"), payload.get("estimated_embedding_tokens")
    )
    total_range = _range_value(
        payload.get("total_tokens"), payload.get("estimated_total_tokens")
    )
    cost_range_usd = payload.get("cost_range_usd")
    if not isinstance(cost_range_usd, dict) and payload.get("pricing_configured"):
        legacy_cost = float(payload.get("estimated_cost_usd") or 0)
        cost_range_usd = {
            "low": legacy_cost,
            "expected": legacy_cost,
            "high": legacy_cost,
        }
        payload["cost_range_usd"] = cost_range_usd
    display_currency, cost_range, secondary_currency, secondary_cost_range = (
        _cost_ranges(payload)
    )

    with st.expander("执行前 Token 与费用预估", expanded=expanded):
        prefix = dict(leading_metrics or {})
        metric_count = len(prefix) + 5
        columns = st.columns(metric_count)
        position = 0
        for label, value in prefix.items():
            columns[position].metric(label, value)
            position += 1
        columns[position].metric(
            "模型调用",
            int(
                payload.get("estimated_model_calls")
                or payload.get("llm_call_count")
                or 0
            ),
        )
        _token_metric(columns[position + 1], "输入 Token", input_range)
        _token_metric(columns[position + 2], "输出 Token", output_range)
        _token_metric(columns[position + 3], "总 Token", total_range)
        columns[position + 4].metric(
            "预计费用",
            _cost_text(cost_range, display_currency),
            help=(
                "预计范围："
                f"{_cost_text({'expected': cost_range.get('low')}, display_currency)}～"
                f"{_cost_text({'expected': cost_range.get('high')}, display_currency)}；"
                f"核对值 {_cost_text(secondary_cost_range, secondary_currency)}"
                if isinstance(cost_range, dict)
                else "缺少必要价格或当前配置为仅统计 Token。"
            ),
        )
        if embedding_range["high"]:
            st.caption(
                f"其中 Embedding 预计 {format_tokens(embedding_range['expected'])} Token，"
                f"范围 {format_tokens(embedding_range['low'])}～{format_tokens(embedding_range['high'])}。"
            )
        if not payload.get("pricing_configured"):
            missing = "、".join(payload.get("missing_price_components", []))
            if str(payload.get("tracking_mode") or "") == "tokens_only":
                st.info("当前模型方案设置为仅统计 Token，因此不显示预计金额。")
            else:
                st.info(
                    f"已估算 Token；{missing or '必要 Token'}价格未配置，因此不猜测金额。"
                )
        confidence_note = f"置信度：{payload.get('confidence_label') or '中等'}"
        if payload.get("history_calibrated"):
            confidence_note += f"；已参考 {int(payload.get('history_sample_count') or 0)} 条历史调用样本"
        else:
            confidence_note += "；历史同类样本不足时使用操作模板"
        st.caption(
            f"模型：{payload.get('model_name') or '未记录'}；{confidence_note}。"
            "区间用于执行前判断规模，不代表供应商最终账单。"
        )
        if isinstance(cost_range, dict) and display_currency == "CNY":
            st.caption(
                f"人民币为主显示；美元核对值 {_cost_text(secondary_cost_range, 'USD')}。"
                f"当前换算系数：1 USD ≈ {normalize_usd_to_cny_rate(payload.get('usd_to_cny_rate')):.6f} CNY。"
            )

        stages = list(payload.get("stages") or [])
        if stages:
            rows = []
            for stage in stages:
                stage_input = _range_value(stage.get("input_tokens"))
                stage_output = _range_value(stage.get("output_tokens"))
                stage_embedding = _range_value(stage.get("embedding_tokens"))
                stage_total = sum(
                    item["expected"] for item in (stage_input, stage_output, stage_embedding)
                )
                stage_usd = stage.get("cost_range_usd")
                stage_cny = stage.get("cost_range_cny")
                if not isinstance(stage_cny, dict) and isinstance(stage_usd, dict):
                    stage_cny = convert_cost_range(
                        stage_usd,
                        source_currency="USD",
                        target_currency="CNY",
                        usd_to_cny_rate=payload.get("usd_to_cny_rate"),
                    )
                rows.append(
                    {
                        "阶段 / Agent": f"{stage.get('stage_name') or '-'} / {stage.get('agent_role') or '-'}",
                        "调用": int(stage.get("call_count") or 0),
                        "输入": format_tokens(stage_input["expected"]),
                        "输出": format_tokens(stage_output["expected"]),
                        "Embedding": format_tokens(stage_embedding["expected"]),
                        "合计": format_tokens(stage_total),
                        "费用（CNY）": _cost_text(stage_cny, "CNY"),
                        "费用（USD）": _cost_text(stage_usd, "USD"),
                    }
                )
            st.dataframe(rows, hide_index=True, width="stretch")

        external_calls = list(payload.get("external_calls") or [])
        if external_calls:
            summary = "；".join(
                f"{item.get('label') or item.get('kind') or '外部调用'}约 {int(item.get('count') or 0)} 次"
                for item in external_calls
            )
            st.caption(f"外部调用：{summary}。这些费用未计入 LLM Token 金额。")
        assumptions = list(payload.get("assumptions") or [])
        if assumptions:
            with st.popover("查看估算依据"):
                for item in assumptions:
                    st.markdown(f"- {item}")

    budget = dict(payload.get("budget") or {})
    reasons = [
        *list(budget.get("warning_reasons") or []),
        *list(budget.get("confirmation_reasons") or []),
    ]
    if reasons:
        st.warning("；".join(dict.fromkeys(str(item) for item in reasons if str(item))) + "。")
    if not budget.get("confirmation_required"):
        return True
    if not confirmation_key:
        st.error("该操作超过模型方案的确认阈值，执行入口需要显式确认。")
        return True
    return bool(
        st.checkbox(
            "我已了解 Token 与费用上界，确认继续执行",
            key=confirmation_key,
        )
    )
