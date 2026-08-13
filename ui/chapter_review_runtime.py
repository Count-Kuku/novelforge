"""Hot-reload-safe adapter for the unified chapter-review workflow."""
from __future__ import annotations

import novelforge.workflows.skills as _skills_api


def _normalize_mode(mode: str) -> str:
    normalized = str(mode or "quick").strip().lower()
    aliases = {
        "quick": "quick",
        "fast": "quick",
        "快速": "quick",
        "快速审阅": "quick",
        "comprehensive": "comprehensive",
        "full": "comprehensive",
        "综合": "comprehensive",
        "综合审阅": "comprehensive",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"quick", "comprehensive"}:
        raise ValueError(f"未知章节审阅模式：{mode}")
    return normalized


def run_chapter_review_by_mode(
    project_name: str,
    chapter_no: int,
    chapter: str,
    *,
    mode: str = "quick",
    story_id: str = "default",
    stream_callback=None,
) -> dict:
    """Call the unified workflow, falling back when Streamlit holds an old facade."""

    normalized_mode = _normalize_mode(mode)
    unified_entry = getattr(_skills_api, "review_chapter_by_mode", None)
    if callable(unified_entry):
        return unified_entry(
            project_name,
            chapter_no,
            chapter,
            mode=normalized_mode,
            story_id=story_id,
            stream_callback=stream_callback,
        )

    if normalized_mode == "quick":
        result = _skills_api.review_chapter(
            project_name,
            chapter_no,
            chapter,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        payload_field = "review"
        report_field = "review_markdown"
        storage_kind = "reviews"
    else:
        result = _skills_api.evaluate_chapter_comprehensive(
            project_name,
            chapter_no,
            chapter,
            story_id=story_id,
            stream_callback=stream_callback,
        )
        payload_field = "evaluation"
        report_field = "report_markdown"
        storage_kind = "evaluation"

    unified = dict(result or {})
    data = dict(unified.get("data") or {})
    data["review_mode"] = normalized_mode
    data["review_payload"] = data.get(payload_field) or {}
    data["review_report"] = str(data.get(report_field) or "")
    data["compatibility_storage"] = storage_kind
    unified["data"] = data
    artifacts = dict(unified.get("artifacts") or {})
    artifacts.update({"review_mode": normalized_mode, "compatibility_storage": storage_kind})
    unified["artifacts"] = artifacts
    return unified
