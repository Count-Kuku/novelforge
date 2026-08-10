"""Execution preflight rendering for the free-writing composer."""
from __future__ import annotations

from novelforge.workflows.interactive_writing import build_writing_fragment_preflight
from ui.common import scoped_widget_key
from ui.llm_preflight import render_preflight_estimate


def render_writing_preflight(
    project_name: str,
    story_id: str,
    session_id: str,
    bundle: dict,
    user_message: str,
    word_count: str,
) -> bool:
    if not str(user_message or "").strip():
        return True
    estimate = build_writing_fragment_preflight(
        bundle,
        str(user_message or "").strip(),
        word_count=word_count,
    )
    estimate_high = int(dict(estimate.get("total_tokens") or {}).get("high") or 0)
    cost_high = round(
        float(dict(estimate.get("cost_range_usd") or {}).get("high") or 0) * 1_000_000
    )
    return render_preflight_estimate(
        estimate,
        confirmation_key=scoped_widget_key(
            "creative_budget_confirm",
            project_name,
            story_id,
            session_id or "new",
            estimate_high,
            cost_high,
        ),
    )
