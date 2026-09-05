"""Implementation slice for the memory facade: story archive/delete/list."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def _set_story_status(project_name: str, story_id: str, next_status: str) -> bool:
    clean_story_id = _memory_api.normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        target = next(
            (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
            None,
        )
        if target is None:
            conn.rollback()
            return False
        target["status"] = next_status
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        active_story_id = clean_story_id if next_status == "active" else next(
            (
                str(row.get("story_id") or "")
                for row in rows
                if str(row.get("status") or "active") != "archived"
            ),
            clean_story_id,
        )
        normalized_index = _memory_api._stories_index_payload_from_rows(rows, active_story_id=active_story_id)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
    return True


def archive_story(project_name: str, story_id: str) -> bool:
    return _set_story_status(project_name, story_id, "archived")


def restore_story(project_name: str, story_id: str) -> bool:
    return _set_story_status(project_name, story_id, "active")


def delete_story(project_name: str, story_id: str) -> bool:
    story_id = _memory_api.normalize_story_id(story_id)

    from novelforge.services.automatic_configuration import delete_automatic_configurations

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current_rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        if not any(str(row.get("story_id") or "") == story_id for row in current_rows):
            conn.rollback()
            return False
        remaining_rows = [
            row
            for row in current_rows
            if str(row.get("story_id") or "") != story_id
        ]
        remaining_stories = [
            {
                "story_id": row.get("story_id", ""),
                "name": row.get("name", ""),
                "description": row.get("description", ""),
                "status": row.get("status", "active"),
                "creation_mode": normalize_creation_mode(row.get("creation_mode")),
                "created_at": row.get("created_at", ""),
                "updated_at": row.get("updated_at", ""),
            }
            for row in remaining_rows
        ]
        if not remaining_stories:
            remaining_stories = [_memory_api._default_story_meta()]
        remaining_ids = {
            str(item.get("story_id") or "")
            for item in remaining_stories
        }
        active_story_id = next(
            (
                str(row.get("story_id") or "")
                for row in remaining_rows
                if row.get("is_active")
                and str(row.get("story_id") or "") in remaining_ids
            ),
            str(remaining_stories[0].get("story_id") or "default"),
        )
        normalized_index = _memory_api._normalize_stories_index_payload({
            "stories": remaining_stories,
            "active_story_id": active_story_id,
        })
        _memory_api.sync_stories_index(conn, normalized_index)
        _memory_api.purge_story_scoped_rows(conn, story_id)
        conn.commit()

    try:
        delete_automatic_configurations(project_name, story_id=story_id)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge.configuration").warning(
            "Story %s was deleted, but automatic settings cleanup failed for %s: %s",
            story_id,
            project_name,
            exc,
        )
    sp = _memory_api.story_path(project_name, story_id)
    if sp.exists():
        import shutil

        shutil.rmtree(str(sp))
    try:
        _memory_api.sync_project_retrieval_assets(project_name)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge.retrieval").warning(
            "Story %s was deleted, but retrieval rebuild failed for %s: %s",
            story_id,
            project_name,
            exc,
        )
    return True


def list_stories(project_name: str) -> list[dict]:
    index = _memory_api.load_stories_index(project_name)
    return list(index.get("stories", []))
