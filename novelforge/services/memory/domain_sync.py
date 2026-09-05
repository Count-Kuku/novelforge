"""Best-effort DB sync/load wrappers for stories, knowledge and retrieval rows."""

from __future__ import annotations

from novelforge.core.schemas import StoriesIndex
from storage.repositories import (
    list_story_rows,
    load_entity_alias_group_rows,
    load_knowledge_category_rows,
    load_pending_knowledge_rows,
    sync_entity_alias_groups,
    sync_knowledge_category,
    sync_pending_knowledge,
    sync_retrieval_source_file,
    sync_stories_index,
)

from .db_availability import (
    _load_project_db_best_effort,
    _mutate_project_db_best_effort,
)
from .runtime_storage import (  # noqa: F401  (re-exported for facade consumers)
    _load_runtime_from_db_best_effort,
    _mutate_workflow_in_db,
    _recover_existing_project_db_if_needed,
    _sync_runtime_to_db_best_effort,
)


def _sync_stories_index_to_db_best_effort(project_name: str, index: dict) -> None:
    _mutate_project_db_best_effort(
        project_name,
        lambda conn: sync_stories_index(conn, index),
        action_label="sync stories index to project database",
    )


def _load_stories_index_from_db_best_effort(project_name: str) -> dict | None:
    rows = _load_project_db_best_effort(
        project_name,
        list_story_rows,
        action_label="load stories index from project database",
    )
    if not rows:
        return {"stories": [], "active_story_id": "default"}
    stories = [
        {
            "story_id": str(row.get("story_id") or ""),
            "name": str(row.get("name") or row.get("story_id") or ""),
            "description": str(row.get("description") or ""),
            "status": str(row.get("status") or "active"),
            "creation_mode": str(row.get("creation_mode") or "planned"),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }
        for row in rows
        if str(row.get("story_id") or "").strip()
    ]
    active_story_id = "default"
    for row in rows:
        if row.get("is_active"):
            active_story_id = str(row.get("story_id") or "default")
            break
    if not any(story["story_id"] == active_story_id for story in stories):
        active_story_id = stories[0]["story_id"] if stories else "default"
    return StoriesIndex(stories=stories, active_story_id=active_story_id).model_dump()


def _sync_knowledge_category_to_db_best_effort(project_name: str, category: str, items: list[dict]) -> None:
    _mutate_project_db_best_effort(
        project_name,
        lambda conn: sync_knowledge_category(conn, category, items),
        action_label="sync knowledge category to project database",
        subject=f"{project_name}/{category}",
    )


def _sync_pending_knowledge_to_db_best_effort(project_name: str, items: list[dict]) -> None:
    _mutate_project_db_best_effort(
        project_name,
        lambda conn: sync_pending_knowledge(conn, items),
        action_label="sync pending knowledge to project database",
    )


def _sync_entity_aliases_to_db_best_effort(project_name: str, items: list[dict]) -> None:
    _mutate_project_db_best_effort(
        project_name,
        lambda conn: sync_entity_alias_groups(conn, items),
        action_label="sync entity aliases to project database",
    )


def _load_knowledge_category_from_db_best_effort(project_name: str, category: str) -> list[dict] | None:
    return _load_project_db_best_effort(
        project_name,
        lambda conn: load_knowledge_category_rows(conn, category),
        action_label="load knowledge category from project database",
        subject=f"{project_name}/{category}",
    )


def _load_pending_knowledge_from_db_best_effort(project_name: str) -> list[dict] | None:
    return _load_project_db_best_effort(
        project_name,
        load_pending_knowledge_rows,
        action_label="load pending knowledge from project database",
    )


def _load_entity_aliases_from_db_best_effort(project_name: str) -> list[dict] | None:
    return _load_project_db_best_effort(
        project_name,
        load_entity_alias_group_rows,
        action_label="load entity aliases from project database",
    )


def _sync_source_to_db_best_effort(project_name: str, callback):
    return _mutate_project_db_best_effort(
        project_name,
        callback,
        action_label="sync source record to project database",
    )


def sync_retrieval_source_file_record(
    project_name: str,
    *,
    relative_path: str,
    title: str,
    content_hash: str | None = None,
    source_type: str = "reference",
    authority: float = 0.0,
    metadata: dict | None = None,
) -> dict:
    result = _sync_source_to_db_best_effort(
        project_name,
        lambda conn: sync_retrieval_source_file(
            conn,
            relative_path=relative_path,
            title=title,
            content_hash=content_hash,
            source_type=source_type,
            authority=authority,
            metadata=metadata,
        ),
    )
    return dict(result or {})


def _sync_retrieval_to_db_best_effort(project_name: str, callback) -> None:
    _mutate_project_db_best_effort(
        project_name,
        callback,
        action_label="sync retrieval index to project database",
    )


def _sync_workflow_to_db_best_effort(project_name: str, callback) -> None:
    _mutate_project_db_best_effort(
        project_name,
        callback,
        action_label="sync workflow run to project database",
    )
