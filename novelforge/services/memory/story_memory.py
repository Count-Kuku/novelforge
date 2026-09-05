"""Implementation slice for the memory facade: creation mode, memory and migration."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def get_story_creation_mode(project_name: str, story_id: str = "default") -> str:
    """Read the story mode from SQLite first, with the normal compatibility path."""

    clean_story_id = _memory_api.normalize_story_id(story_id)
    rows = _memory_api.list_stories(project_name)
    target = next(
        (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
        None,
    )
    if target is None:
        raise ValueError(f"故事不存在：{clean_story_id}")
    return normalize_creation_mode(target.get("creation_mode"))


def set_story_creation_mode(
    project_name: str,
    story_id: str,
    creation_mode: str,
) -> dict:
    """Change the story's UI/workflow mode without deleting any story asset."""

    clean_story_id = _memory_api.normalize_story_id(story_id)
    clean_creation_mode = normalize_creation_mode(creation_mode)
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    normalized_index: dict | None = None
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
        target = next(
            (row for row in rows if str(row.get("story_id") or "") == clean_story_id),
            None,
        )
        if target is None:
            conn.rollback()
            raise ValueError(f"故事不存在：{clean_story_id}")
        target["creation_mode"] = clean_creation_mode
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        normalized_index = _memory_api._stories_index_payload_from_rows(rows)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()

    if normalized_index is None:
        raise RuntimeError("Story mode update did not produce an index.")
    return next(
        dict(story)
        for story in normalized_index.get("stories", [])
        if story.get("story_id") == clean_story_id
    )


def load_story_memory_overrides(project_name: str, story_id: str) -> dict:
    """Load only a story's persisted override layer, using SQLite first."""

    story_id = _memory_api.normalize_story_id(story_id)
    if story_id == "default":
        return {}
    db_overrides = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="story_memory_overrides",
        logical_key="memory_overrides",
        story_id=story_id,
    )
    if isinstance(db_overrides, dict):
        overrides = db_overrides
    else:
        overrides = None
    overrides_path = _memory_api._story_memory_overrides_path(project_name, story_id)
    if overrides is None and not overrides_path.exists():
        return {}
    if overrides is None:
        try:
            overrides = _memory_api.json.loads(overrides_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(overrides, dict):
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                overrides_path,
                asset_type="story_memory_overrides",
                logical_key="memory_overrides",
                story_id=story_id,
                title="Story Memory Overrides",
                payload=overrides,
            )
    if not isinstance(overrides, dict):
        return {}
    return dict(overrides)


def load_story_memory(project_name: str, story_id: str) -> dict:
    base = _memory_api.load_memory(project_name)
    overrides = load_story_memory_overrides(project_name, story_id)
    if not overrides:
        return base
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, list) and isinstance(base.get(key), list):
            # 基于 key 去重合并，防止前缀匹配优化未命中时产生重复条目
            seen: set[str] = set()
            deduped: list = []
            for item in base[key] + value:
                item_key = str(item.get("name") or item.get("title") or item) if isinstance(item, dict) else str(item)
                if item_key not in seen:
                    seen.add(item_key)
                    deduped.append(item)
            merged[key] = deduped
        elif value is not None:
            merged[key] = value
    return merged


def save_story_memory(project_name: str, story_id: str, memory: dict):
    if story_id == "default":
        _memory_api.save_memory(project_name, memory)
        return

    base = _memory_api.load_memory(project_name)
    overrides: dict = {}
    for key, value in (memory or {}).items():
        base_value = base.get(key)
        if value == base_value:
            continue
        # 使用前缀匹配检测仅追加的新条目；若条目被插入到列表开头或中间，则整体值会存入覆盖层，
        # 下次加载时会基于 key 去重合并，因此数据一致性不会受损。
        if isinstance(value, list) and isinstance(base_value, list) and value[:len(base_value)] == base_value:
            extra_items = value[len(base_value):]
            if extra_items:
                overrides[key] = extra_items
        else:
            overrides[key] = value

    path = _memory_api._story_memory_overrides_path(project_name, story_id)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="story_memory_overrides",
        logical_key="memory_overrides",
        story_id=story_id,
        title="Story Memory Overrides",
        payload=overrides,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_story_chapter_summaries(project_name: str, story_id: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_summaries",
        logical_key="chapter_summaries",
        story_id=story_id,
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    path = _memory_api._story_chapter_summaries_path(project_name, story_id)
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        items = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
        if items:
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                path,
                asset_type="chapter_summaries",
                logical_key="chapter_summaries",
                story_id=story_id,
                title="Chapter Summaries",
                payload=items,
            )
        return items
    except Exception:
        return []


def save_story_chapter_summaries(project_name: str, story_id: str, summaries: list[dict]):
    path = _memory_api._story_chapter_summaries_path(project_name, story_id)
    normalized = [item for item in list(summaries or []) if isinstance(item, dict)]
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="chapter_summaries",
        logical_key="chapter_summaries",
        story_id=story_id,
        title="Chapter Summaries",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def migrate_project_to_stories(project_name: str) -> bool:
    marker = _memory_api.project_path(project_name) / ".migrated"
    if marker.exists():
        return False
    legacy_memory: dict = {}
    legacy_memory_path = _memory_api.project_path(project_name) / "memory.json"
    if legacy_memory_path.exists():
        try:
            loaded_legacy_memory = _memory_api.json.loads(legacy_memory_path.read_text(encoding="utf-8"))
            if isinstance(loaded_legacy_memory, dict):
                legacy_memory = loaded_legacy_memory
        except (_memory_api.json.JSONDecodeError, OSError) as exc:
            _memory_api.logging.getLogger("novelforge.storage").warning(
                "Failed to read legacy memory during story migration for %s: %s",
                project_name,
                exc,
            )
    sp = _memory_api.story_path(project_name, "default")
    sp.mkdir(parents=True, exist_ok=True)

    migratable = [
        ("outline.md", "outline.md"),
        ("outline.discussion.json", "outline.discussion.json"),
        ("creative_profile.json", "creative_profile.json"),
        ("creative_profile.discussion.json", "creative_profile.discussion.json"),
        ("volumes", "volumes"),
        ("arcs", "arcs"),
        ("chapter_outlines", "chapter_outlines"),
        ("chapters", "chapters"),
        ("reviews", "reviews"),
        ("analysis", "analysis"),
        ("evaluation", "evaluation"),
        ("runs", "runs"),
    ]
    moved_any = False
    for src_name, dst_name in migratable:
        src = _memory_api.project_path(project_name) / src_name
        dst = sp / dst_name
        if src.exists():
            if dst.exists():
                continue
            src.rename(dst)
            moved_any = True

    conflict_src = _memory_api.project_path(project_name) / "retrieval" / "conflict_resolutions.json"
    conflict_dst = sp / "retrieval" / "conflict_resolutions.json"
    if conflict_src.exists():
        conflict_dst.parent.mkdir(parents=True, exist_ok=True)
        conflict_src.rename(conflict_dst)

    summaries = legacy_memory.get("chapter_summaries", [])
    if summaries:
        save_story_chapter_summaries(project_name, "default", list(summaries))

    memory = _memory_api.load_memory(project_name)
    if "chapter_summaries" in memory:
        memory["chapter_summaries"] = []
        _memory_api.save_memory(project_name, memory)

    idx_path = _memory_api.project_path(project_name) / "stories" / "index.json"
    if not idx_path.exists():
        now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        default_meta = _memory_api.StoryMeta(
            story_id="default",
            name="默认故事",
            description="",
            status="active",
            created_at=now,
            updated_at=now,
        )
        idx = _memory_api.StoriesIndex(stories=[default_meta], active_story_id="default")
        _memory_api.save_stories_index(project_name, idx.model_dump())

    marker.write_text("")
    _memory_api.sync_project_retrieval_assets(project_name)
    return moved_any


def _story_path_from_project_path(project_name: str, story_id: str, *parts: str) -> _memory_api.Path:
    return _memory_api.story_path(project_name, story_id).joinpath(*parts)
