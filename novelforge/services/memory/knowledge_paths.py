"""Implementation slice for the memory facade: knowledge paths and base CRUD."""

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

def knowledge_dir_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def knowledge_category_path(project_name: str, category: str) -> _memory_api.Path:
    safe_category = str(category or "").strip()
    if safe_category not in _memory_api.KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    return knowledge_dir_path(project_name) / f"{safe_category}.json"


def knowledge_entities_dir_path(project_name: str) -> _memory_api.Path:
    path = knowledge_dir_path(project_name) / "entities"
    path.mkdir(parents=True, exist_ok=True)
    return path


def entity_aliases_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "aliases.json"


def extraction_plan_templates_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "extraction_plans.json"


def pending_knowledge_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "pending.json"


def auto_review_runs_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "auto_review_runs.json"


def auto_review_policy_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "auto_review_policy.json"


# 默认审核策略：全自动确认（用户偏好「提取后无需人工逐条审核」）。
# 仅保留两道与策略无关的硬门槛（见 evaluate_pending_auto_review_decision）：
#   1) typed_errors —— 结构校验失败，确认会破坏 schema；
#   2) issue —— 提取阶段质检标记的问题条目。
# 这两道独立于本策略，无法也不应通过放宽策略放开；其余（置信度/证据强度/缺证据/分类强制人工）全部放开。
# 纠错兜底由「直接编辑条目」与「LLM 对话改条目」两条修改途径承担，而非事前人工审核。
DEFAULT_AUTO_REVIEW_POLICY = {
    "min_confidence": 0.0,
    "min_evidence_strength": 0.0,
    "grade_a_confidence": 0.75,
    "grade_a_evidence_strength": 0.65,
    "allow_grade_b_auto_confirm": True,
    "require_evidence": False,
    "manual_review_categories": [],
}


def _load_json_list(path: _memory_api.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def load_knowledge_category(project_name: str, category: str) -> list[dict]:
    db_items = _memory_api._load_knowledge_category_from_db_best_effort(project_name, category)
    if db_items is not None:
        return db_items
    json_items = _load_json_list(knowledge_category_path(project_name, category))
    if db_items == [] and json_items:
        _memory_api._sync_knowledge_category_to_db_best_effort(project_name, category, json_items)
    return json_items


def save_knowledge_category(project_name: str, category: str, items: list[dict]):
    path = knowledge_category_path(project_name, category)
    normalized = [normalize_typed_knowledge_item(item, category) for item in items if isinstance(item, dict)]
    _memory_api._sync_knowledge_category_to_db_best_effort(project_name, category, normalized)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_knowledge_base(project_name: str) -> dict[str, list[dict]]:
    return {
        category: load_knowledge_category(project_name, category)
        for category in _memory_api.KNOWLEDGE_CATEGORIES
    }


# ---- Entity-Fact 查询门面（refactor 2 P0/P1）----
# domain 层不得直接碰 sqlite；统一经此门面走 entity_query 的 Entity-Fact-Relation 读取。
# 注意：`memory` 顶层命名空间的 load_entities/load_entity_facts/load_entity_relations 是
# 既有 re-export 的 repository 版（收 conn），因此这里的服务门面用带前缀的名字避免被覆盖。
