"""Shared rendering for source-ingestion task estimates."""
from __future__ import annotations

from ui.llm_preflight import render_preflight_estimate


def render_ingestion_task_estimate(
    estimate: dict,
    *,
    expanded: bool = False,
    confirmation_key: str | None = None,
) -> bool:
    return render_preflight_estimate(
        estimate,
        expanded=expanded,
        confirmation_key=confirmation_key,
        leading_metrics={"资料片段": int(estimate.get("segment_count") or 0)},
    )
