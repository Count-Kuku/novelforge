"""Shared rendering for source-ingestion task estimates."""
from __future__ import annotations

from ui.llm_preflight import render_preflight_estimate


def render_ingestion_task_estimate(
    estimate: dict,
    *,
    expanded: bool = False,
    confirmation_key: str | None = None,
    interactive_confirmation: bool = True,
) -> bool:
    return render_preflight_estimate(
        estimate,
        expanded=expanded,
        confirmation_key=confirmation_key,
        interactive_confirmation=interactive_confirmation,
        leading_metrics={"资料片段": int(estimate.get("segment_count") or 0)},
    )
