"""Implementation slice for the memory facade: auto review policy and runs."""

from __future__ import annotations

from novelforge.services import memory as _memory_api
from novelforge.domain.knowledge_types import normalize_typed_knowledge_item
from storage.repositories import entity_query
from storage.repositories.knowledge import (
    fetch_knowledge_entity_rows,
    load_knowledge_evidence_rows,
    load_knowledge_revision_rows,
    summarize_knowledge_storage_health,
)

def load_auto_review_runs(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_auto_review_run_rows, "auto review runs")
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(_memory_api.auto_review_runs_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_auto_review_runs(conn, json_items),
        )
    return json_items


def save_auto_review_runs(project_name: str, runs: list[dict]):
    path = _memory_api.auto_review_runs_path(project_name)
    normalized = [item for item in runs if isinstance(item, dict)]
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_auto_review_runs(conn, normalized),
    )


def normalize_auto_review_policy(policy: dict | None) -> dict:
    raw = policy if isinstance(policy, dict) else {}
    normalized = dict(_memory_api.DEFAULT_AUTO_REVIEW_POLICY)
    for key in ["min_confidence", "min_evidence_strength", "grade_a_confidence", "grade_a_evidence_strength"]:
        try:
            value = float(raw.get(key, normalized[key]))
        except (TypeError, ValueError):
            value = float(normalized[key])
        normalized[key] = max(0.0, min(1.0, value))
    normalized["allow_grade_b_auto_confirm"] = bool(raw.get("allow_grade_b_auto_confirm", normalized["allow_grade_b_auto_confirm"]))
    normalized["require_evidence"] = bool(raw.get("require_evidence", normalized["require_evidence"]))
    categories = raw.get("manual_review_categories", normalized["manual_review_categories"])
    if not isinstance(categories, list):
        categories = normalized["manual_review_categories"]
    normalized["manual_review_categories"] = [
        str(category)
        for category in categories
        if str(category) in _memory_api.KNOWLEDGE_CATEGORIES
    ]
    return normalized


def load_auto_review_policy(project_name: str) -> dict:
    db_policy = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_auto_review_policy_row, "auto review policy")
    if db_policy is not None:
        return normalize_auto_review_policy(db_policy)
    path = _memory_api.auto_review_policy_path(project_name)
    if not path.exists():
        return dict(_memory_api.DEFAULT_AUTO_REVIEW_POLICY)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    normalized = normalize_auto_review_policy(raw)
    if db_policy == [] or db_policy == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_auto_review_policy(conn, normalized),
        )
    return normalized


def save_auto_review_policy(project_name: str, policy: dict) -> dict:
    normalized = normalize_auto_review_policy(policy)
    path = _memory_api.auto_review_policy_path(project_name)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_auto_review_policy(conn, normalized),
    )
    return normalized


def append_auto_review_run(project_name: str, run: dict) -> dict:
    runs = load_auto_review_runs(project_name)
    normalized = dict(run or {})
    normalized["run_id"] = normalized.get("run_id") or f"auto_review_{_memory_api.uuid4().hex}"
    normalized["created_at"] = normalized.get("created_at") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    normalized["status"] = normalized.get("status") or "active"
    runs.append(normalized)
    save_auto_review_runs(project_name, runs[-200:])
    return normalized
