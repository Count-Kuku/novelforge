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


def rename_project_automatic_configurations(
    old_project_name: str,
    new_project_name: str,
    *,
    data_path: Path = Path("data"),
) -> int:
    """Move project-scoped automatic settings to keys derived from the new name."""

    initialize_global_db(data_path)
    with open_global_db(data_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        moved = 0
        try:
            rows = conn.execute(
                "SELECT * FROM automatic_configuration_state WHERE project_name=?",
                (str(old_project_name or "").strip(),),
            ).fetchall()
            if not rows:
                conn.commit()
                return 0
            collision = conn.execute(
                "SELECT 1 FROM automatic_configuration_state WHERE project_name=? LIMIT 1",
                (str(new_project_name or "").strip(),),
            ).fetchone()
            if collision:
                raise ValueError("目标项目已存在自动配置，不能覆盖迁移。")
            for raw in rows:
                state = dict(raw)
                old_key = str(state["config_key"])
                new_key = automatic_configuration_key(
                    new_project_name,
                    str(state.get("story_id") or ""),
                    str(state.get("operation") or ""),
                )
                revisions = conn.execute(
                    "SELECT * FROM automatic_configuration_revisions WHERE config_key=? ORDER BY created_at,rowid",
                    (old_key,),
                ).fetchall()
                conn.execute("DELETE FROM automatic_configuration_state WHERE config_key=?", (old_key,))
                conn.execute(
                    """
                    INSERT INTO automatic_configuration_state (
                        config_key, project_name, story_id, operation, settings_json,
                        locked_fields_json, source_revision_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_key, new_project_name, state.get("story_id") or "",
                        state.get("operation") or "", state.get("settings_json") or "{}",
                        state.get("locked_fields_json") or "[]", state.get("source_revision_id"),
                        state.get("created_at"), state.get("updated_at"),
                    ),
                )
                for raw_revision in revisions:
                    revision = dict(raw_revision)
                    conn.execute(
                        """
                        INSERT INTO automatic_configuration_revisions (
                            revision_id, config_key, project_name, story_id, operation,
                            before_json, after_json, diff_json, reasons_json, signals_json,
                            locked_fields_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            revision["revision_id"], new_key, new_project_name,
                            revision.get("story_id") or "", revision.get("operation") or "",
                            revision.get("before_json") or "{}", revision.get("after_json") or "{}",
                            revision.get("diff_json") or "{}", revision.get("reasons_json") or "[]",
                            revision.get("signals_json") or "{}", revision.get("locked_fields_json") or "[]",
                            revision.get("created_at"),
                        ),
                    )
                moved += 1
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        return moved


def copy_story_automatic_configurations(
    project_name: str,
    source_story_id: str,
    target_story_id: str,
    *,
    data_path: Path = Path("data"),
) -> int:
    """Copy effective settings and locks; the target starts a fresh revision chain."""

    if not str(source_story_id or "").strip() or not str(target_story_id or "").strip():
        raise ValueError("源故事和目标故事 ID 不能为空。")
    if str(source_story_id).strip() == str(target_story_id).strip():
        raise ValueError("不能把自动配置复制回同一个故事。")
    initialize_global_db(data_path)
    with open_global_db(data_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        copied = 0
        try:
            collision = conn.execute(
                "SELECT 1 FROM automatic_configuration_state WHERE project_name=? AND story_id=? LIMIT 1",
                (project_name, target_story_id),
            ).fetchone()
            if collision:
                raise ValueError("目标故事已存在自动配置，不能覆盖复制。")
            rows = conn.execute(
                "SELECT * FROM automatic_configuration_state WHERE project_name=? AND story_id=?",
                (project_name, source_story_id),
            ).fetchall()
            for raw in rows:
                source = dict(raw)
                operation = str(source.get("operation") or "")
                target_key = automatic_configuration_key(project_name, target_story_id, operation)
                revision_id = f"auto_revision_{uuid4().hex}"
                conn.execute(
                    """
                    INSERT INTO automatic_configuration_state (
                        config_key, project_name, story_id, operation, settings_json,
                        locked_fields_json, source_revision_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'), strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                    """,
                    (
                        target_key, project_name, target_story_id, operation,
                        source.get("settings_json") or "{}", source.get("locked_fields_json") or "[]",
                        revision_id,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO automatic_configuration_revisions (
                        revision_id, config_key, project_name, story_id, operation,
                        before_json, after_json, diff_json, reasons_json, signals_json,
                        locked_fields_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, '{}', ?, '{}', ?, '{}', ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                    """,
                    (
                        revision_id, target_key, project_name, target_story_id, operation,
                        source.get("settings_json") or "{}",
                        '["从源故事复制自动配置与用户锁定项。"]',
                        source.get("locked_fields_json") or "[]",
                    ),
                )
                copied += 1
            conn.commit()
            return copied
        except Exception:
            conn.rollback()
            raise


def delete_automatic_configurations(
    project_name: str,
    *,
    story_id: str | None = None,
    data_path: Path = Path("data"),
) -> int:
    initialize_global_db(data_path)
    with open_global_db(data_path) as conn:
        if story_id is None:
            cursor = conn.execute(
                "DELETE FROM automatic_configuration_state WHERE project_name=?",
                (project_name,),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM automatic_configuration_state WHERE project_name=? AND story_id=?",
                (project_name, story_id),
            )
        conn.commit()
        return int(cursor.rowcount or 0)
