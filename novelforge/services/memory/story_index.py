"""Implementation slice for the memory facade: story index, meta and paths."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def _default_story_meta() -> dict:
    return _memory_api.StoryMeta(
        story_id="default",
        name="默认故事",
        description="",
        status="active",
        creation_mode=DEFAULT_CREATION_MODE,
        created_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
        updated_at=_memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
    ).model_dump()


def _normalize_stories_index_payload(index: dict | None) -> dict:
    normalized = _memory_api.StoriesIndex.model_validate(index or {}).model_dump()
    stories: list[dict] = []
    seen_story_ids: set[str] = set()
    for story in normalized.get("stories", []):
        try:
            clean_story_id = _memory_api.normalize_story_id(story.get("story_id", ""))
        except ValueError as exc:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Skipping invalid story ID in stories index: %s", exc
            )
            continue
        if clean_story_id in seen_story_ids:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Skipping duplicate story ID in stories index: %s", clean_story_id
            )
            continue
        clean_story = dict(story)
        clean_story["story_id"] = clean_story_id
        clean_story["creation_mode"] = normalize_creation_mode(clean_story.get("creation_mode"))
        stories.append(clean_story)
        seen_story_ids.add(clean_story_id)

    if not stories:
        stories.append(_default_story_meta())
        seen_story_ids.add("default")

    try:
        active_story_id = _memory_api.normalize_story_id(normalized.get("active_story_id", "default"))
    except ValueError:
        active_story_id = "default"
    if active_story_id not in seen_story_ids:
        active_story_id = stories[0]["story_id"]

    return _memory_api.StoriesIndex(stories=stories, active_story_id=active_story_id).model_dump()


def stories_index_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "stories" / "index.json"


def story_path(project_name: str, story_id: str) -> _memory_api.Path:
    stories_root = _memory_api.project_path(project_name) / "stories"
    target = stories_root / _memory_api.normalize_story_id(story_id)
    resolved_root = stories_root.resolve()
    resolved_target = target.resolve()
    if resolved_root != resolved_target and resolved_root not in resolved_target.parents:
        raise ValueError("Invalid story path.")
    return target


def _stories_index_payload_from_rows(
    rows: list[dict],
    *,
    active_story_id: str = "",
) -> dict:
    stories = [
        {
            "story_id": row.get("story_id", ""),
            "name": row.get("name", ""),
            "description": row.get("description", ""),
            "status": row.get("status", "active"),
            "creation_mode": normalize_creation_mode(row.get("creation_mode")),
            "created_at": row.get("created_at", ""),
            "updated_at": row.get("updated_at", ""),
        }
        for row in rows
        if str(row.get("story_id") or "")
    ]
    if not stories:
        stories = [_default_story_meta()]
    story_ids = {str(item.get("story_id") or "") for item in stories}
    resolved_active_id = str(active_story_id or "")
    if resolved_active_id not in story_ids:
        resolved_active_id = next(
            (
                str(row.get("story_id") or "")
                for row in rows
                if row.get("is_active")
                and str(row.get("story_id") or "") in story_ids
            ),
            str(stories[0].get("story_id") or "default"),
        )
    return _normalize_stories_index_payload({
        "stories": stories,
        "active_story_id": resolved_active_id,
    })


def _story_chapter_summaries_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "chapter_summaries.json"


def _story_memory_overrides_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "memory_overrides.json"


def _story_rules_overrides_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "rules_overrides.json"


def _project_prompt_options_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "prompt_options.json"


def _story_prompt_options_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "prompt_options.json"


def _project_rule_conflict_resolutions_path(project_name: str) -> _memory_api.Path:
    return _memory_api.project_path(project_name) / "rule_conflict_resolutions.json"


def _story_rule_conflict_resolutions_path(project_name: str, story_id: str) -> _memory_api.Path:
    return story_path(project_name, story_id) / "rule_conflict_resolutions.json"


def _load_stories_index_file(project_name: str) -> dict:
    path = stories_index_path(project_name)
    if not path.exists():
        return _normalize_stories_index_payload(None)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        return _normalize_stories_index_payload(raw)
    except Exception:
        return _normalize_stories_index_payload(None)


def load_stories_index(project_name: str) -> dict:
    db_index = _memory_api._load_stories_index_from_db_best_effort(project_name)
    if db_index and db_index.get("stories"):
        return _normalize_stories_index_payload(db_index)

    path = stories_index_path(project_name)
    if path.exists():
        normalized = _load_stories_index_file(project_name)
        if db_index is not None and normalized.get("stories"):
            _memory_api._sync_stories_index_to_db_best_effort(project_name, normalized)
        return normalized

    if not db_index or not db_index.get("stories"):
        idx = _normalize_stories_index_payload({"stories": [_default_story_meta()], "active_story_id": "default"})
        save_stories_index(project_name, idx)
        return idx

    return _normalize_stories_index_payload(db_index)


def save_stories_index(project_name: str, index: dict):
    normalized = _normalize_stories_index_payload(index)
    path = stories_index_path(project_name)
    _memory_api._sync_stories_index_to_db_best_effort(project_name, normalized)


def get_active_story_id(project_name: str) -> str:
    index = load_stories_index(project_name)
    return str(index.get("active_story_id", "default") or "default")


def set_active_story(project_name: str, story_id: str):
    clean_story_id = _memory_api.normalize_story_id(story_id)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        if clean_story_id not in {str(row.get("story_id") or "") for row in rows}:
            conn.rollback()
            raise ValueError(f"故事不存在：{clean_story_id}")
        normalized_index = _stories_index_payload_from_rows(
            rows,
            active_story_id=clean_story_id,
        )
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
