"""Implementation slice for the memory facade: story create/rename/merge."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def create_story(
    project_name: str,
    name: str,
    description: str = "",
    creation_mode: str = DEFAULT_CREATION_MODE,
) -> dict:
    clean_name = str(name or "").strip()
    clean_creation_mode = normalize_creation_mode(creation_mode)
    if not clean_name:
        raise ValueError("故事名称不能为空。")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    normalized_index: dict | None = None
    sp: _memory_api.Path | None = None
    meta: _memory_api.StoryMeta | None = None
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_rows = [dict(row) for row in _memory_api.list_story_rows(conn)]
            existing_ids = {
                str(row.get("story_id") or "")
                for row in current_rows
            }
            base_story_id = _memory_api.normalize_story_id(_memory_api._story_id_slug(clean_name))
            story_id = base_story_id
            if story_id in existing_ids:
                counter = 2
                while f"{base_story_id}_{counter}" in existing_ids:
                    counter += 1
                    if counter > 1000:
                        raise RuntimeError(f"无法为故事名 '{clean_name}' 生成唯一 ID：计数器已超上限。")
                story_id = _memory_api.normalize_story_id(f"{base_story_id}_{counter}")

            sp = _memory_api.story_path(project_name, story_id)
            if sp.exists():
                raise FileExistsError(f"故事目录已存在但未登记：{story_id}")
            sp.mkdir(parents=True, exist_ok=False)

            now = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
            meta = _memory_api.StoryMeta(
                story_id=story_id,
                name=clean_name,
                description=description,
                status="active",
                creation_mode=clean_creation_mode,
                created_at=now,
                updated_at=now,
            )
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
                for row in current_rows
            ]
            stories.append(meta.model_dump())
            active_story_id = next(
                (
                    str(row.get("story_id") or "")
                    for row in current_rows
                    if row.get("is_active")
                ),
                "",
            )
            if not active_story_id or active_story_id == "default":
                active_story_id = story_id
            normalized_index = _memory_api._normalize_stories_index_payload({
                "stories": stories,
                "active_story_id": active_story_id,
            })
            _memory_api.sync_stories_index(conn, normalized_index)
            conn.commit()
    except Exception:
        if sp is not None:
            try:
                sp.rmdir()
            except OSError as rollback_exc:
                _memory_api.logging.getLogger("novelforge.storage").warning(
                    "Failed to remove story directory after create rollback %s: %s",
                    sp,
                    rollback_exc,
                )
        raise
    if meta is None:
        raise RuntimeError("Story creation did not produce metadata.")
    return meta.model_dump()


def rename_story(project_name: str, story_id: str, name: str, description: str | None = None) -> dict:
    clean_story_id = _memory_api.normalize_story_id(story_id)
    clean_name = str(name or "").strip()
    if not clean_name:
        raise ValueError("故事名称不能为空。")

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
            raise ValueError(f"故事不存在：{clean_story_id}")
        target["name"] = clean_name
        if description is not None:
            target["description"] = str(description or "").strip()
        target["updated_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")
        normalized_index = _memory_api._stories_index_payload_from_rows(rows)
        _memory_api.sync_stories_index(conn, normalized_index)
        conn.commit()
    return next(
        dict(story)
        for story in normalized_index.get("stories", [])
        if story.get("story_id") == clean_story_id
    )



def copy_story_settings(
    project_name: str,
    source_story_id: str,
    target_story_id: str,
    *,
    include_discussions: bool = True,
):
    """复制故事级创作配置、讨论工件、Prompt 选项、规则、旧 memory 覆盖层和正式优先设定。"""
    profile = _memory_api.load_creative_profile(project_name, source_story_id)
    _memory_api.save_creative_profile(
        project_name,
        profile,
        target_story_id,
        mark_configured=bool(profile.get("is_configured")),
    )

    discussion_artifact = (
        _memory_api.load_creative_profile_discussion_artifact(project_name, source_story_id)
        if include_discussions
        else {}
    )
    if discussion_artifact:
        _memory_api.save_creative_profile_discussion_artifact(
            project_name,
            discussion_artifact.get("discussion", {}),
            discussion_artifact.get("report_markdown", ""),
            target_story_id,
        )

    _memory_api.save_story_memory(project_name, target_story_id, _memory_api.load_story_memory(project_name, source_story_id))
    _memory_api.save_story_rules(project_name, target_story_id, _memory_api.load_story_rules(project_name, source_story_id))
    copied_prompt_options: list[dict] = []
    for source_option in _memory_api.load_story_prompt_options(project_name, source_story_id):
        clone = dict(source_option)
        clone["source"] = "story_copy"
        copied_prompt_options.append(clone)
    _memory_api.save_story_prompt_options(project_name, target_story_id, copied_prompt_options)
    _memory_api.save_rule_conflict_resolutions(
        project_name,
        "story",
        _memory_api.load_rule_conflict_resolutions(project_name, "story", source_story_id),
        target_story_id,
    )

    from novelforge.domain.setting_knowledge import copy_story_core_settings_to_story

    core_result = copy_story_core_settings_to_story(project_name, source_story_id, target_story_id)

    _memory_api.sync_project_retrieval_assets(project_name)
    return core_result


def _merge_list_values(source: list | None, target: list | None) -> list:
    seen: set[str] = set()
    merged: list = []
    for item in (source or []) + (target or []):
        if item is None:
            continue
        if isinstance(item, dict):
            key = str(item.get("name") or item.get("title") or "").strip()
            if not key:
                merged.append(item)
                continue
        else:
            key = str(item).strip()
            if not key:
                merged.append(item)
                continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def merge_story_to_project_memory(project_name: str, story_id: str, field_resolutions: dict[str, _memory_api.Any] | None = None) -> dict:
    from novelforge.core.merge import build_merge_plan

    base = _memory_api.load_memory(project_name)
    story = _memory_api.load_story_memory(project_name, story_id)
    plan = build_merge_plan(story, base, source_label="故事", target_label="项目", base_path="memory")
    resolved = {}
    for opt in plan:
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[opt.path.replace("memory.", "")] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[opt.path.replace("memory.", "")] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[opt.path.replace("memory.", "")] = field_resolutions[opt.path]
        else:
            resolved[opt.path.replace("memory.", "")] = opt.source_value

    merged = dict(base)
    for key, value in resolved.items():
        merged[key] = value
    _memory_api.save_memory(project_name, merged)

    overrides_path = _memory_api._story_memory_overrides_path(project_name, story_id)
    if overrides_path.exists():
        overrides_path.unlink()
    _memory_api.sync_project_retrieval_assets(project_name)
    return merged


def merge_project_to_story_memory(project_name: str, story_id: str, field_resolutions: dict[str, _memory_api.Any] | None = None) -> dict:
    from novelforge.core.merge import build_merge_plan

    base = _memory_api.load_memory(project_name)
    story = _memory_api.load_story_memory(project_name, story_id)
    plan = build_merge_plan(base, story, source_label="项目", target_label="故事", base_path="memory")
    resolved = {}
    for opt in plan:
        key = opt.path.replace("memory.", "")
        if key == "chapter_summaries":
            continue
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[key] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[key] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[key] = field_resolutions[opt.path]
        else:
            resolved[key] = opt.source_value

    overrides: dict = {}
    for key, value in resolved.items():
        if base.get(key) != value:
            overrides[key] = value
    path = _memory_api._story_memory_overrides_path(project_name, story_id)
    _memory_api.sync_project_retrieval_assets(project_name)
    return {**base, **overrides}


def merge_story_rules_to_project(project_name: str, story_id: str) -> dict:
    project_rules = _memory_api.load_project_rules(project_name)
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(project_rules, story_rules)
    _memory_api.save_project_rules(project_name, merged)
    path = _memory_api._story_rules_overrides_path(project_name, story_id)
    if path.exists():
        path.unlink()
    return merged


def merge_project_rules_to_story(project_name: str, story_id: str) -> dict:
    project_rules = _memory_api.load_project_rules(project_name)
    _memory_api.save_story_rules(project_name, story_id, project_rules)
    return project_rules


def _merge_rules_dedup(target_rules: dict, source_rules: dict) -> dict:
    from novelforge.core.merge import _merge_dedup

    merged = dict(target_rules)
    for scope in _memory_api.RULE_SCOPES:
        source_items = source_rules.get(scope, [])
        if source_items:
            existing = merged.get(scope, [])
            merged[scope] = _merge_dedup(existing, source_items)
    return _memory_api.normalize_rules(merged)


def merge_project_rules_to_global(project_name: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    project_rules = _memory_api.load_project_rules(project_name)
    merged = _merge_rules_dedup(global_rules, project_rules)
    _memory_api.save_global_rules(merged)
    return merged


def merge_story_rules_to_global(project_name: str, story_id: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(global_rules, story_rules)
    _memory_api.save_global_rules(merged)
    return merged


def merge_global_rules_to_project(project_name: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    project_rules = _memory_api.load_project_rules(project_name)
    merged = _merge_rules_dedup(project_rules, global_rules)
    _memory_api.save_project_rules(project_name, merged)
    return merged


def merge_global_rules_to_story(project_name: str, story_id: str) -> dict:
    global_rules = _memory_api.load_global_rules()
    story_rules = _memory_api.load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(story_rules, global_rules)
    _memory_api.save_story_rules(project_name, story_id, merged)
    return merged
