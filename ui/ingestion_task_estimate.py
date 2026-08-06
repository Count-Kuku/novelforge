"""Shared rendering for source-ingestion task estimates."""
from __future__ import annotations

import streamlit as st


def _format_tokens(value: int) -> str:
    number = int(value or 0)
    if number >= 1_000_000:
        return f"{number / 1_000_000:.2f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)


def render_ingestion_task_estimate(estimate: dict, *, expanded: bool = False) -> None:
    with st.expander("执行前用量与费用估算", expanded=expanded):
        metric_cols = st.columns(5)
        metric_cols[0].metric("资料片段", int(estimate.get("segment_count") or 0))
        metric_cols[1].metric("模型调用", int(estimate.get("llm_call_count") or 0))
        metric_cols[2].metric("输入 Token", _format_tokens(estimate.get("estimated_input_tokens", 0)))
        metric_cols[3].metric("输出 Token", _format_tokens(estimate.get("estimated_output_tokens", 0)))
        metric_cols[4].metric("Embedding", _format_tokens(estimate.get("estimated_embedding_tokens", 0)))
        if estimate.get("pricing_configured"):
            st.success(f"按当前模型配置估算费用：约 ${float(estimate.get('estimated_cost_usd') or 0):.4f}")
        else:
            missing = "、".join(estimate.get("missing_price_components", [])) or "Token"
            st.info(f"已估算 Token；{missing}费率尚未配置，因此不猜测金额。可在“模型配置”中填写每百万 Token 价格。")
        st.caption(
            f"模型：{estimate.get('model_name') or '未记录'}；"
            "估算用于执行前判断规模，不代表供应商实际账单。"
        )
