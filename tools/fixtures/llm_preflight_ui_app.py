from __future__ import annotations

import streamlit as st

from ui.llm_preflight import render_preflight_estimate


with st.form("preflight-test"):
    render_preflight_estimate(
        {
        "enabled": True,
        "model_name": "test-model",
        "estimated_model_calls": 2,
        "input_tokens": {"low": 100, "expected": 200, "high": 300},
        "output_tokens": {"low": 50, "expected": 100, "high": 200},
        "embedding_tokens": {"low": 0, "expected": 0, "high": 0},
        "total_tokens": {"low": 150, "expected": 300, "high": 500},
        "cost_range_usd": {"low": 0.001, "expected": 0.002, "high": 0.004},
        "pricing_configured": True,
        "confidence_label": "中等",
        "history_calibrated": False,
        "stages": [
            {
                "stage_name": "生成",
                "agent_role": "generator",
                "call_count": 2,
                "input_tokens": {"low": 100, "expected": 200, "high": 300},
                "output_tokens": {"low": 50, "expected": 100, "high": 200},
                "embedding_tokens": {"low": 0, "expected": 0, "high": 0},
                "cost_range_usd": {"low": 0.001, "expected": 0.002, "high": 0.004},
            }
        ],
        "external_calls": [{"label": "搜索 API", "count": 1}],
        "assumptions": ["测试估算依据。"],
        "budget": {"status": "within_budget", "confirmation_required": False},
        },
        expanded=True,
    )
    st.form_submit_button("执行")
