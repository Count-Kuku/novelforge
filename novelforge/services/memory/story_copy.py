"""Implementation slice for the memory facade: story copy."""

from __future__ import annotations

import hashlib
import re

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

_STORY_COPY_CHAPTER_DIRS = {
    "chapters",
    "chapter_outlines",
    "reviews",
    "analysis",
    "evaluation",
    "runs",
}

_STORY_COPY_TOP_LEVEL_JSON_MIRRORS = {
    "chapter_summaries.json",
    "creative_profile.discussion.json",
    "creative_profile.json",
    "memory_overrides.json",
    "outline.discussion.json",
    "prompt_options.json",
    "rule_conflict_resolutions.json",
    "rules_overrides.json",
}


def _story_copy_path_is_known_json_mirror(relative_path: _memory_api.Path) -> bool:
    parts = tuple(part.casefold() for part in relative_path.parts)
    if len(parts) == 1:
        return parts[0] in _STORY_COPY_TOP_LEVEL_JSON_MIRRORS
    if len(parts) != 2:
        return False
    directory, file_name = parts
    if directory == "runs":
        return file_name.endswith(".json")
    patterns = {
        "reviews": r"chapter_\d+\.json",
        "evaluation": r"chapter_\d+\.json",
        "chapter_outlines": r"chapter_\d+\.(?:meta|discussion)\.json",
        "volumes": r"volume_\d+\.(?:meta|discussion)\.json",
        "arcs": r"arc_\d+\.(?:meta|discussion|chapter_plan)\.json",
    }
    pattern = patterns.get(directory)
    return bool(pattern and _memory_api.re.fullmatch(pattern, file_name))


def _story_db_json_mirror_paths(conn, story_id: str) -> set[str]:
    prefix = f"stories/{story_id}/"
    rows = conn.execute(
        """
        SELECT asset.relative_path
        FROM asset_files AS asset
        INNER JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE asset.story_id = ? AND asset.deleted_at IS NULL
        """,
        (story_id,),
    ).fetchall()
    paths: set[str] = set()
    for row in rows:
        project_relative = str(row["relative_path"] or "").replace("\\", "/")
        if project_relative.startswith(prefix) and project_relative.casefold().endswith(".json"):
            paths.add(project_relative[len(prefix):])
    return paths


def _story_copy_file_is_included(
    relative_path: _memory_api.Path,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
    db_json_mirror_paths: set[str] | None = None,
) -> bool:
    parts = relative_path.parts
    top_level = parts[0] if parts else ""
    if not include_chapters and top_level in _STORY_COPY_CHAPTER_DIRS:
        return False
    if not include_summaries and relative_path.name == "chapter_summaries.json":
        return False
    if not include_discussions:
        if top_level in {"volumes", "arcs"}:
            return False
        if "discussion" in relative_path.name.casefold():
            return False
    normalized_relative_path = "/".join(relative_path.parts)
    if (
        relative_path.suffix.casefold() == ".json"
        and (
            _story_copy_path_is_known_json_mirror(relative_path)
            or normalized_relative_path in (db_json_mirror_paths or set())
        )
    ):
        return False
    return True


def _copy_branch_folder(branch_id: str) -> str:
    clean = str(branch_id or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", clean)
    return f"{slug[:48]}_{hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]}"


def _target_story_file_path(relative_path: _memory_api.Path, branch_id_map: dict[str, str] | None) -> _memory_api.Path:
    parts = list(relative_path.parts)
    if len(parts) >= 2 and parts[0] == "branches":
        source_folder = parts[1]
        for source_branch_id, target_branch_id in (branch_id_map or {}).items():
            if _copy_branch_folder(source_branch_id) == source_folder:
                parts[1] = _copy_branch_folder(target_branch_id)
                break
    return _memory_api.Path(*parts)


def _copy_story_files(
    source_dir: _memory_api.Path,
    target_dir: _memory_api.Path,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
    db_json_mirror_paths: set[str] | None = None,
    branch_id_map: dict[str, str] | None = None,
) -> None:
    import shutil

    if not source_dir.exists():
        return
    source_root = source_dir.resolve()
    target_root = target_dir.resolve()
    for item in source_dir.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Story copies do not follow symbolic links: {item}")
        if not item.is_file():
            continue
        resolved_item = item.resolve()
        if source_root not in resolved_item.parents:
            raise ValueError(f"Story file escaped its source directory: {item}")
        relative_path = item.relative_to(source_dir)
        if not _story_copy_file_is_included(
            relative_path,
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
            db_json_mirror_paths=db_json_mirror_paths,
        ):
            continue
        target_file = (target_dir / _target_story_file_path(relative_path, branch_id_map)).resolve()
        if target_root not in target_file.parents:
            raise ValueError(f"Story copy target escaped its directory: {relative_path}")
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(resolved_item), str(target_file))


def _rollback_story_copy(project_name: str, target_story_id: str, original_index: dict) -> list[str]:
    import shutil

    errors: list[str] = []
    normalized_index: dict | None = None
    database_cleaned = False
    try:
        if _memory_api._project_db_marked_unavailable(project_name):
            raise RuntimeError(f"Project database is unavailable for {project_name}.")
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_rows = [
                dict(row)
                for row in _memory_api.list_story_rows(conn)
                if str(row.get("story_id") or "") != target_story_id
            ]
            current_stories = [
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
            if not current_stories:
                current_stories = [_memory_api._default_story_meta()]
            active_story_id = next(
                (
                    str(row.get("story_id") or "")
                    for row in current_rows
                    if row.get("is_active")
                ),
                "",
            )
            current_ids = {str(item.get("story_id") or "") for item in current_stories}
            original_active_id = str(original_index.get("active_story_id") or "")
            if active_story_id not in current_ids:
                active_story_id = (
                    original_active_id
                    if original_active_id in current_ids
                    else str(current_stories[0].get("story_id") or "default")
                )
            normalized_index = _memory_api._normalize_stories_index_payload({
                "stories": current_stories,
                "active_story_id": active_story_id,
            })
            _memory_api.sync_stories_index(conn, normalized_index)
            _memory_api.purge_story_scoped_rows(conn, target_story_id)
            conn.commit()
        database_cleaned = True
    except Exception as exc:
        errors.append(f"database cleanup failed: {exc}")

    target_dir = _memory_api.story_path(project_name, target_story_id)
    if database_cleaned:
        try:
            if target_dir.exists():
                shutil.rmtree(str(target_dir))
        except Exception as exc:
            errors.append(f"file cleanup failed: {exc}")
    elif target_dir.exists():
        errors.append("file cleanup skipped because database cleanup failed")

    if database_cleaned:
        try:
            from novelforge.services.automatic_configuration import delete_automatic_configurations

            delete_automatic_configurations(project_name, story_id=target_story_id)
        except Exception as exc:
            errors.append(f"automatic configuration cleanup failed: {exc}")

    if database_cleaned:
        try:
            _memory_api.sync_project_retrieval_assets(project_name)
        except Exception as exc:
            _memory_api.logging.getLogger("novelforge").warning(
                "Failed to refresh retrieval assets after rolling back story copy: "
                "project=%s target=%s error=%s",
                project_name,
                target_story_id,
                exc,
            )
    return errors


def copy_story(project_name: str, source_story_id: str, new_name: str,
               *, include_discussions: bool = True, include_summaries: bool = True,
               include_chapters: bool = True) -> dict:
    source_story_id = _memory_api.normalize_story_id(source_story_id)
    original_index = _memory_api._normalize_stories_index_payload(_memory_api.load_stories_index(project_name))
    source_story = next(
        (
            story
            for story in original_index.get("stories", [])
            if str(story.get("story_id") or "") == source_story_id
        ),
        None,
    )
    if source_story is None:
        raise ValueError(f"故事不存在：{source_story_id}")

    target_id = _memory_api._story_id_slug(new_name)
    existing_ids = {
        str(story.get("story_id") or "")
        for story in original_index.get("stories", [])
    }
    if target_id in existing_ids:
        counter = 2
        while f"{target_id}_{counter}" in existing_ids:
            counter += 1
            if counter > 1000:
                raise RuntimeError(f"无法为故事名 '{new_name}' 生成唯一 ID：计数器已超上限。")
        target_id = f"{target_id}_{counter}"

    # create_story validates and creates the directory before committing the
    # index, so compensation is only needed after it returns an owned target.
    meta: dict | None = None
    try:
        created_meta = _memory_api.create_story(
            project_name,
            new_name,
            str(source_story.get("description") or ""),
            normalize_creation_mode(source_story.get("creation_mode")),
        )
        meta = created_meta
        target_id = str(created_meta["story_id"])
        src_dir = _memory_api.story_path(project_name, source_story_id)
        dst_dir = _memory_api.story_path(project_name, target_id)
        dst_dir.mkdir(parents=True, exist_ok=True)

        clone_result: dict = {}
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            source_json_mirror_paths = _story_db_json_mirror_paths(conn, source_story_id)
            clone_result = _memory_api.clone_story_storage_rows(
                conn,
                source_story_id,
                target_id,
                include_discussions=include_discussions,
                include_summaries=include_summaries,
                include_chapters=include_chapters,
            )
            conn.commit()

        _copy_story_files(
            src_dir,
            dst_dir,
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
            db_json_mirror_paths=source_json_mirror_paths,
            branch_id_map=clone_result.get("branch_id_map"),
        )

        _memory_api.copy_story_settings(
            project_name,
            source_story_id,
            target_id,
            include_discussions=include_discussions,
            # clone_story_storage_rows already copied every branch's knowledge
            # with remapped identity; legacy core copying would duplicate it.
            include_core_knowledge=False,
        )
        from novelforge.services.automatic_configuration import copy_story_automatic_configurations

        copy_story_automatic_configurations(project_name, source_story_id, target_id)
        _memory_api.sync_project_retrieval_assets(project_name)
        return meta
    except Exception as exc:
        if meta is not None:
            cleanup_errors = _rollback_story_copy(
                project_name,
                str(meta.get("story_id") or ""),
                original_index,
            )
            if cleanup_errors:
                raise RuntimeError(
                    "Story copy failed and rollback was incomplete: " + "; ".join(cleanup_errors)
                ) from exc
        raise
