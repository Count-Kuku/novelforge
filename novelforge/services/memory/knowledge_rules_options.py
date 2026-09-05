"""Implementation slice for the memory facade: rules and prompt options."""

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

def load_story_rules(project_name: str, story_id: str) -> dict:
    db_rules = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_rules_payload(conn, "story", story_id),
        "story rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    path = _memory_api._story_rules_overrides_path(project_name, story_id)
    if not path.exists():
        return _memory_api.normalize_rules(None)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        normalized = _memory_api.normalize_rules(raw)
    except Exception:
        return _memory_api.normalize_rules(None)
    if db_rules == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
        )
    return normalized


def save_story_rules(project_name: str, story_id: str, rules: dict):
    path = _memory_api._story_rules_overrides_path(project_name, story_id)
    normalized = _memory_api.normalize_rules(rules)
    if all(len(v) == 0 for v in normalized.values()):
        if path.exists():
            path.unlink()
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
        )
        return
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
    )


def load_global_rules() -> dict:
    db_rules = _memory_api._load_global_from_db_best_effort(
        lambda conn: _memory_api.load_rules_payload(conn, "global"),
        "global rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    _memory_api.GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _memory_api.GLOBAL_RULES_PATH.exists():
        rules = _memory_api.normalize_rules(None)
        save_global_rules(rules)
        return rules

    try:
        rules = _memory_api.json.loads(_memory_api.GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
    except (_memory_api.json.JSONDecodeError, OSError):
        rules = _memory_api.normalize_rules(None)
        save_global_rules(rules)
        return rules
    normalized = _memory_api.normalize_rules(rules)
    if normalized != rules:
        save_global_rules(normalized)
    elif db_rules == {}:
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_rules_payload(conn, "global", normalized)
        )
    return normalized


def save_global_rules(rules: dict):
    normalized = _memory_api.normalize_rules(rules)
    _memory_api._sync_global_to_db_best_effort(
        lambda conn: _memory_api.sync_rules_payload(conn, "global", normalized)
    )


def load_project_rules(project_name: str) -> dict:
    db_rules = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_rules_payload(conn, "project"),
        "project rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    path = _memory_api.project_path(project_name) / "rules.json"
    if not path.exists():
        rules = _memory_api.normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules

    try:
        rules = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except (_memory_api.json.JSONDecodeError, OSError):
        rules = _memory_api.normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules
    normalized = _memory_api.normalize_rules(rules)
    if normalized != rules:
        save_project_rules(project_name, normalized)
    elif db_rules == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "project", normalized),
        )
    return normalized


def save_project_rules(project_name: str, rules: dict):
    path = _memory_api.project_path(project_name) / "rules.json"
    normalized = _memory_api.normalize_rules(rules)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_rules_payload(conn, "project", normalized),
    )


def _load_prompt_options_file(path: _memory_api.Path, scope: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _memory_api.normalize_prompt_options_payload(raw, scope=scope)


def _save_prompt_options_file(path: _memory_api.Path, options: list[dict], scope: str) -> list[dict]:
    normalized = _memory_api.normalize_prompt_options_payload(options, scope=scope)
    return normalized


def load_global_prompt_options() -> list[dict]:
    _memory_api.GLOBAL_PROMPT_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_items = _memory_api._load_global_from_db_best_effort(
        lambda conn: _memory_api.load_prompt_options_payload(conn, "global"),
        "global prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="global")
    items = _load_prompt_options_file(_memory_api.GLOBAL_PROMPT_OPTIONS_PATH, "global")
    if db_items == [] and items:
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "global", items)
        )
    return items


def save_global_prompt_options(options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api.GLOBAL_PROMPT_OPTIONS_PATH, options, "global")
    _memory_api._sync_global_to_db_best_effort(
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "global", normalized)
    )
    return normalized


def load_project_prompt_options(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_prompt_options_payload(conn, "project"),
        "project prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="project")
    items = _load_prompt_options_file(_memory_api._project_prompt_options_path(project_name), "project")
    if db_items == [] and items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "project", items),
        )
    return items


def save_project_prompt_options(project_name: str, options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api._project_prompt_options_path(project_name), options, "project")
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "project", normalized),
    )
    return normalized


def load_story_prompt_options(project_name: str, story_id: str = "default") -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_prompt_options_payload(conn, "story", story_id),
        "story prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="story")
    items = _load_prompt_options_file(_memory_api._story_prompt_options_path(project_name, story_id), "story")
    if db_items == [] and items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "story", items, story_id),
        )
    return items


def save_story_prompt_options(project_name: str, story_id: str, options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api._story_prompt_options_path(project_name, story_id), options, "story")
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "story", normalized, story_id),
    )
    return normalized


def upsert_prompt_option(project_name: str, layer: str, option: dict, story_id: str = "default") -> dict:
    normalized_layer = str(layer or "story").strip().lower()
    if normalized_layer == "global":
        existing = load_global_prompt_options()
        scope = "global"
    elif normalized_layer == "project":
        existing = load_project_prompt_options(project_name)
        scope = "project"
    elif normalized_layer == "story":
        existing = load_story_prompt_options(project_name, story_id)
        scope = "story"
    else:
        raise ValueError(f"Unknown prompt option layer: {layer}")

    normalized_option = _memory_api.normalize_prompt_options_payload([option], scope=scope)[0]
    updated = []
    replaced = False
    for item in existing:
        if item.get("id") == normalized_option["id"]:
            updated.append(normalized_option)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(normalized_option)

    if normalized_layer == "global":
        save_global_prompt_options(updated)
    elif normalized_layer == "project":
        save_project_prompt_options(project_name, updated)
    else:
        save_story_prompt_options(project_name, story_id, updated)
    return normalized_option


def delete_prompt_option(project_name: str, layer: str, option_id: str, story_id: str = "default") -> bool:
    target_id = str(option_id or "").strip()
    normalized_layer = str(layer or "story").strip().lower()
    if normalized_layer == "global":
        existing = load_global_prompt_options()
        kept = [item for item in existing if item.get("id") != target_id]
        save_global_prompt_options(kept)
    elif normalized_layer == "project":
        existing = load_project_prompt_options(project_name)
        kept = [item for item in existing if item.get("id") != target_id]
        save_project_prompt_options(project_name, kept)
    elif normalized_layer == "story":
        existing = load_story_prompt_options(project_name, story_id)
        kept = [item for item in existing if item.get("id") != target_id]
        save_story_prompt_options(project_name, story_id, kept)
    else:
        raise ValueError(f"Unknown prompt option layer: {layer}")
    return len(kept) != len(existing)
