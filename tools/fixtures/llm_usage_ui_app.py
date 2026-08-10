"""Streamlit fixture for tools/verify_llm_usage_ui.py."""
from __future__ import annotations

import ui.llm_usage as usage


usage.load_llm_settings = lambda: {
    "display_currency": "CNY",
    "pricing_currency": "CNY",
    "usd_to_cny_rate": 7.142857,
}

usage.summarize_llm_usage = lambda **kwargs: {
    "request_count": 1,
    "total_tokens": 15,
    "cost_usd": 0.001,
    "priced_request_count": 1,
    "unpriced_request_count": 0,
    "provider_cost_count": 1,
    "estimated_request_count": 0,
    "has_usage": True,
}
usage.list_daily_llm_usage = lambda **kwargs: [{
    "usage_date": "2026-08-10",
    "request_count": 1,
    "input_tokens": 10,
    "cached_input_tokens": 0,
    "output_tokens": 5,
    "embedding_tokens": 0,
    "total_tokens": 15,
    "cost_usd": 0.001,
    "unpriced_request_count": 0,
}]
usage.list_llm_usage_breakdown = lambda **kwargs: [{
    "bucket": "model-a",
    "request_count": 1,
    "total_tokens": 15,
    "cost_usd": 0.001,
    "unpriced_request_count": 0,
}]
usage.list_recent_llm_usage_events = lambda **kwargs: [{
    "occurred_at": "2026-08-10T00:00:00+00:00",
    "project_name": "demo",
    "story_id": "default",
    "agent_role": "writer",
    "operation": "chapter.write",
    "provider": "deepseek",
    "reported_model": "model-a",
    "endpoint_type": "chat",
    "total_tokens": 15,
    "cost_usd": 0.001,
    "usage_status": "exact",
    "cost_source": "provider_reported",
}]

usage.render_usage_dashboard(key_prefix="usage-ui-test")
