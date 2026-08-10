"""Streamlit fixture for confirmation-gate and read-only preflight semantics."""
from __future__ import annotations

import streamlit as st

from ui.llm_preflight import render_preflight_estimate


ESTIMATE = {
    "enabled": True,
    "model_name": "test-model",
    "estimated_model_calls": 1,
    "input_tokens": {"low": 100, "expected": 200, "high": 300},
    "output_tokens": {"low": 50, "expected": 100, "high": 200},
    "embedding_tokens": {"low": 0, "expected": 0, "high": 0},
    "total_tokens": {"low": 150, "expected": 300, "high": 500},
    "cost_range_usd": {"low": 0.001, "expected": 0.002, "high": 0.004},
    "pricing_configured": True,
    "confidence_label": "中等",
    "history_calibrated": False,
    "budget": {
        "status": "confirmation_required",
        "confirmation_required": True,
        "confirmation_reasons": ["超过确认阈值"],
    },
}

interactive_result = render_preflight_estimate(ESTIMATE)
readonly_result = render_preflight_estimate(
    ESTIMATE,
    interactive_confirmation=False,
)
st.text(f"interactive_result={interactive_result}")
st.text(f"readonly_result={readonly_result}")
