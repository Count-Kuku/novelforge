"""Project-level memory (项目概览) and project creation bootstrap."""

from __future__ import annotations

import json
import logging

from novelforge.services import memory as _memory_api
from storage.repositories import get_project_meta, upsert_project_meta

from .db_availability import _initialize_project_db_best_effort
from .json_mirrors import _write_json_mirror
from .project_registry import (
    ensure_project_path,
    project_is_discoverable,
    project_data_exists,
    project_path,
    register_project,
    normalize_project_name,
)
from .runtime_storage import (
    _load_runtime_from_db_best_effort,
    _sync_runtime_to_db_best_effort,
)

DEFAULT_MEMORY = {
    "title": "",
    "genre": "",
    "canon_mode": "",
    "au_rules": [],
    "world": [],
    "characters": [],
    "relationships": [],
    "timeline": [],
    "foreshadowing": [],
    "active_constraints": [],
    "chapter_summaries": [],
    "locations": [],
    "organizations": [],
    "power_systems": [],
    "relationship_graph": [],
}
MEMORY_META_FIELDS = ("title", "genre")
KNOWLEDGE_CATEGORIES = {
    "characters": "角色知识",
    "items": "物品与道具",
    "abilities": "技能与能力",
    "world_rules": "世界观规则",
    "locations": "地点资料",
    "organizations": "组织资料",
    "timeline_events": "事件与时间线",
    "relationships": "角色关系",
    "writing_style": "写作风格",
    "dialogue_style": "对白风格",
    "narrative_techniques": "写作手法",
}


def create_project(project_name: str) -> str:
    normalized_name = normalize_project_name(project_name)
    if project_is_discoverable(normalized_name):
        raise FileExistsError("Project already exists.")
    if project_data_exists(normalized_name):
        raise FileExistsError("Project data directory already exists but is not recognized as a project.")

    ensure_project_path(normalized_name)
    _initialize_project_db_best_effort(normalized_name)
    _memory_api.load_stories_index(normalized_name)
    load_memory(normalized_name)
    _memory_api.load_creative_profile(normalized_name)
    _memory_api.load_project_rules(normalized_name)
    _memory_api.knowledge_dir_path(normalized_name)
    _memory_api.save_pending_knowledge_items(normalized_name, _memory_api.load_pending_knowledge_items(normalized_name))
    _memory_api.long_reference_batches_path(normalized_name)
    _memory_api.retrieval_sources_path(normalized_name)
    register_project(normalized_name, make_active=True)
    return normalized_name


def normalize_memory(project_name: str, memory: dict | None) -> dict:
    normalized = DEFAULT_MEMORY.copy()
    if isinstance(memory, dict):
        normalized.update(memory)

    normalized["title"] = normalized.get("title") or project_name

    for key in ["au_rules", "world", "characters", "relationships", "timeline", "foreshadowing", "active_constraints", "chapter_summaries", "locations", "organizations", "power_systems", "relationship_graph"]:
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    genre = normalized.get("genre", "")
    normalized["genre"] = genre if isinstance(genre, str) else str(genre)
    canon_mode = normalized.get("canon_mode", "")
    normalized["canon_mode"] = canon_mode if isinstance(canon_mode, str) else str(canon_mode)
    return normalized


def slim_memory_for_storage(project_name: str, memory: dict | None) -> dict:
    normalized = normalize_memory(project_name, memory)
    return {
        "title": normalized.get("title") or project_name,
        "genre": normalized.get("genre", ""),
    }


def sync_project_retrieval_assets(project_name: str):
    try:
        from novelforge.services.retrieval import rebuild_retrieval_assets

        rebuild_retrieval_assets(project_name, build_vectors=False)
    except Exception as exc:
        logging.getLogger("novelforge").warning(
            "Failed to sync retrieval assets for project %s: %s",
            project_name, exc,
        )


def load_memory(project_name: str) -> dict:
    db_meta = _load_runtime_from_db_best_effort(
        project_name,
        lambda conn: get_project_meta(conn, project_name) or {},
        "project metadata",
    )
    if db_meta is not None:
        return normalize_memory(project_name, {
            "title": db_meta.get("title") or project_name,
            "genre": db_meta.get("genre") or "",
        })
    path = project_path(project_name) / "memory.json"

    if not path.exists():
        memory = normalize_memory(project_name, None)
        save_memory(project_name, slim_memory_for_storage(project_name, memory))
        return memory

    try:
        memory = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        memory = normalize_memory(project_name, None)
        save_memory(project_name, slim_memory_for_storage(project_name, memory))
        return memory
    return normalize_memory(project_name, memory)


def save_memory(project_name: str, memory: dict):
    path = project_path(project_name) / "memory.json"
    normalized = slim_memory_for_storage(project_name, memory)
    _write_json_mirror(path, normalized)
    _sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: upsert_project_meta(
            conn,
            project_name=project_name,
            title=normalized.get("title") or project_name,
            genre=normalized.get("genre") or "",
        ),
    )
    sync_project_retrieval_assets(project_name)
