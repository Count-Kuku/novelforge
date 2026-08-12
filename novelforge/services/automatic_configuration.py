"""Explainable, lock-aware automatic workflow configuration."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from uuid import uuid4

from storage import initialize_global_db, open_global_db
from storage.repositories import (
    list_automatic_configuration_revision_rows,
    load_automatic_configuration_state_row,
    save_automatic_configuration_row,
)


AUTO_CONFIGURATION_FIELDS = (
    "retrieval_depth",
    "retrieval_top_k",
    "extraction_categories",
    "context_budget",
    "batch_size",
)


def estimate_project_source_chars(project_name: str) -> int:
    """Estimate user-supplied corpus size without reading every source body."""

    try:
        from novelforge.services.memory import list_long_reference_batches

        return sum(
            max(int(batch.get("content_char_count") or 0), 0)
            for batch in list_long_reference_batches(project_name)
        )
    except Exception:
        return 0


def automatic_configuration_key(project_name: str, story_id: str, operation: str) -> str:
    scope = f"{project_name.strip()}\0{story_id.strip()}\0{operation.strip()}"
    return f"auto_{hashlib.sha256(scope.encode('utf-8')).hexdigest()[:32]}"


def collect_automatic_configuration_signals(
    project_name: str,
    *,
    story_id: str = "",
    goal: str = "",
    source_chars: int = 0,
) -> dict:
    usage: dict = {}
    feedback_counts: Counter[str] = Counter()
    try:
        from novelforge.services.llm_usage import summarize_llm_usage

        usage = summarize_llm_usage(project_name=project_name, story_id=story_id or None)
    except Exception:
        usage = {}
    try:
        from novelforge.services.memory import load_retrieval_feedback

        feedback_counts.update(
            str(item.get("rating") or "") for item in load_retrieval_feedback(project_name)
        )
    except Exception:
        pass
    request_count = int(usage.get("request_count") or 0)
    return {
        "goal": str(goal or "").strip(),
        "source_chars": max(int(source_chars or 0), 0),
        "historic_request_count": request_count,
        "historic_average_tokens": (
            int(usage.get("total_tokens") or 0) // request_count if request_count else 0
        ),
        "historic_average_cost_usd": (
            float(usage.get("cost_usd") or 0) / request_count if request_count else 0.0
        ),
        "quality_feedback": dict(feedback_counts),
    }


def recommend_automatic_configuration(signals: dict) -> tuple[dict, list[str]]:
    source_chars = max(int(signals.get("source_chars") or 0), 0)
    goal = str(signals.get("goal") or "").lower()
    feedback = Counter(signals.get("quality_feedback") or {})
    reasons: list[str] = []
    if source_chars >= 500_000:
        settings = {
            "retrieval_depth": "deep",
            "retrieval_top_k": 14,
            "context_budget": 16_000,
            "batch_size": 5,
        }
        reasons.append("资料规模较大，提升检索深度和上下文预算，并缩小每批处理量。")
    elif source_chars >= 80_000:
        settings = {
            "retrieval_depth": "balanced",
            "retrieval_top_k": 12,
            "context_budget": 14_000,
            "batch_size": 8,
        }
        reasons.append("资料规模中等，采用均衡检索与批量配置。")
    else:
        settings = {
            "retrieval_depth": "focused",
            "retrieval_top_k": 10,
            "context_budget": 12_000,
            "batch_size": 12,
        }
        reasons.append("资料规模较小，采用聚焦检索以降低延迟和成本。")

    categories = ["characters", "world_rules", "relationships", "timeline_events", "constraints"]
    category_signals = (
        ("对白", "dialogue_style"),
        ("风格", "writing_style"),
        ("地点", "locations"),
        ("组织", "organizations"),
        ("能力", "abilities"),
        ("道具", "items"),
    )
    selected_signals = [category for keyword, category in category_signals if keyword in goal]
    if selected_signals:
        categories.extend(selected_signals)
        reasons.append("根据当前创作目标补充了针对性的提取类别。")
    settings["extraction_categories"] = list(dict.fromkeys(categories))

    bad_feedback = feedback["irrelevant"] + feedback["wrong"]
    good_feedback = feedback["helpful"] + feedback["priority"]
    if bad_feedback > good_feedback and bad_feedback >= 2:
        settings["retrieval_top_k"] = max(settings["retrieval_top_k"] - 2, 4)
        reasons.append("近期无关/错误检索反馈偏多，收紧候选数量以提高精度。")
    elif good_feedback >= max(bad_feedback * 2, 3):
        settings["retrieval_top_k"] = min(settings["retrieval_top_k"] + 2, 18)
        reasons.append("近期检索反馈良好，适度扩大候选范围以提升召回。")

    average_tokens = int(signals.get("historic_average_tokens") or 0)
    average_cost = float(signals.get("historic_average_cost_usd") or 0)
    if average_tokens >= 30_000 or average_cost >= 0.15:
        settings["context_budget"] = max(int(settings["context_budget"] * 0.8), 8_000)
        settings["batch_size"] = max(settings["batch_size"] - 2, 3)
        reasons.append("历史单次消耗偏高，自动收紧上下文和批量大小。")
    return settings, reasons


def load_automatic_configuration(
    project_name: str,
    story_id: str,
    operation: str,
    *,
    data_path: Path = Path("data"),
) -> dict:
    initialize_global_db(data_path)
    key = automatic_configuration_key(project_name, story_id, operation)
    with open_global_db(data_path) as conn:
        return load_automatic_configuration_state_row(conn, key)


def configure_operation_automatically(
    project_name: str,
    story_id: str,
    operation: str,
    *,
    goal: str = "",
    source_chars: int = 0,
    locked_fields: list[str] | None = None,
    data_path: Path = Path("data"),
) -> dict:
    initialize_global_db(data_path)
    config_key = automatic_configuration_key(project_name, story_id, operation)
    with open_global_db(data_path) as conn:
        previous = load_automatic_configuration_state_row(conn, config_key)
    before = dict(previous.get("settings") or {})
    active_locks = set(
        locked_fields if locked_fields is not None else previous.get("locked_fields") or []
    ) & set(AUTO_CONFIGURATION_FIELDS)
    signals = collect_automatic_configuration_signals(
        project_name, story_id=story_id, goal=goal, source_chars=source_chars
    )
    recommended, reasons = recommend_automatic_configuration(signals)
    after = dict(before)
    for field, value in recommended.items():
        if field not in active_locks:
            after[field] = value
    diff = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in AUTO_CONFIGURATION_FIELDS
        if before.get(field) != after.get(field)
    }
    if active_locks:
        reasons.append("已保留用户锁定字段，自动配置未覆盖这些值。")
    revision = None
    if diff or set(previous.get("locked_fields") or []) != active_locks:
        revision = {
            "revision_id": f"auto_revision_{uuid4().hex}",
            "before": before,
            "after": after,
            "diff": diff,
            "reasons": reasons,
            "signals": signals,
        }
    state = {
        "config_key": config_key,
        "project_name": project_name,
        "story_id": story_id,
        "operation": operation,
        "settings": after,
        "locked_fields": sorted(active_locks),
        "source_revision_id": revision and revision["revision_id"] or previous.get("source_revision_id"),
    }
    with open_global_db(data_path) as conn:
        saved = save_automatic_configuration_row(conn, state=state, revision=revision)
    return {**saved, "diff": diff, "reasons": reasons, "signals": signals}


def list_automatic_configuration_revisions(
    project_name: str,
    story_id: str,
    operation: str,
    *,
    limit: int = 50,
    data_path: Path = Path("data"),
) -> list[dict]:
    initialize_global_db(data_path)
    key = automatic_configuration_key(project_name, story_id, operation)
    with open_global_db(data_path) as conn:
        return list_automatic_configuration_revision_rows(conn, key, limit=limit)
