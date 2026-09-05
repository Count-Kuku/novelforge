"""Implementation slice for the memory facade: revisions, evidence, aliases and templates."""

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

def load_knowledge_revisions(project_name: str, knowledge_id: str) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_knowledge_revision_rows(conn, knowledge_id),
        "knowledge revisions",
    )
    return result if isinstance(result, list) else []


def load_knowledge_evidence(project_name: str, knowledge_id: str) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_knowledge_evidence_rows(conn, knowledge_id),
        "knowledge evidence",
    )
    return result if isinstance(result, list) else []


def load_knowledge_storage_health(project_name: str) -> dict:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        summarize_knowledge_storage_health,
        "knowledge storage health",
    )
    return result if isinstance(result, dict) else {}


def load_entity_aliases(project_name: str) -> list[dict]:
    db_items = _memory_api._load_entity_aliases_from_db_best_effort(project_name)
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(_memory_api.entity_aliases_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_entity_aliases_to_db_best_effort(project_name, json_items)
    return json_items


def save_entity_aliases(project_name: str, items: list[dict]):
    path = _memory_api.entity_aliases_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._sync_entity_aliases_to_db_best_effort(project_name, normalized)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_extraction_plan_templates(project_name: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="extraction_plan_templates",
        logical_key="templates",
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    return _memory_api._load_json_list(_memory_api.extraction_plan_templates_path(project_name))


def save_extraction_plan_templates(project_name: str, items: list[dict]):
    path = _memory_api.extraction_plan_templates_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="extraction_plan_templates",
        logical_key="templates",
        title="Extraction Plan Templates",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_pending_knowledge_items(project_name: str) -> list[dict]:
    db_items = _memory_api._load_pending_knowledge_from_db_best_effort(project_name)
    if db_items is not None:
        return db_items
    json_items = _memory_api._load_json_list(_memory_api.pending_knowledge_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_pending_knowledge_to_db_best_effort(project_name, json_items)
    return json_items


def save_pending_knowledge_items(project_name: str, items: list[dict]):
    path = _memory_api.pending_knowledge_path(project_name)
    normalized = [
        normalize_typed_knowledge_item(item, str(item.get("category") or ""))
        for item in items
        if isinstance(item, dict)
    ]
    _memory_api._sync_pending_knowledge_to_db_best_effort(project_name, normalized)
