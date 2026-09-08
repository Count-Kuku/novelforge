"""Service facade for project reference releases and story-local copies."""

from __future__ import annotations

from typing import Any, Iterable

from novelforge.services import memory as _memory_api
from storage.repositories.story_reference_libraries import (
    archive_reference_library as _archive_reference_library,
    bind_story_library as _bind_story_library,
    create_reference_library as _create_reference_library,
    create_reference_library_release as _create_reference_library_release,
    ensure_reference_libraries_for_project as _ensure_reference_libraries_for_project,
    ensure_story_reference_state as _ensure_story_reference_state,
    list_reference_libraries as _list_reference_libraries,
    list_reference_library_releases as _list_reference_library_releases,
    list_story_library_bindings as _list_story_library_bindings,
    list_visible_knowledge_ids as _list_visible_knowledge_ids,
    load_reference_library_release_sources as _load_reference_library_release_sources,
    load_story_reference_state as _load_story_reference_state,
    load_reference_library as _load_reference_library,
    load_reference_library_release as _load_reference_library_release,
    load_story_library_binding as _load_story_library_binding,
    migrate_legacy_story_library as _migrate_legacy_story_library,
    mark_story_reference_strict as _mark_story_reference_strict,
    resolve_story_reference_context as _resolve_story_reference_context,
    unbind_story_library as _unbind_story_library,
)
from storage.repositories.branches import default_branch_id


def _with_db(project_name: str):
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    return _memory_api.open_project_db(_memory_api.project_path(project_name).resolve())


def _check_branch(conn, story_id: str, branch_id: str | None, *, require_active: bool = False) -> None:
    if not branch_id:
        raise ValueError("故事资料必须绑定到明确分支。")
    row = conn.execute(
        "SELECT branch_id, status FROM story_branches WHERE branch_id = ? AND story_id = ?",
        (branch_id, story_id),
    ).fetchone()
    if row is None or (require_active and str(row[1] or "") != "active"):
        raise ValueError("分支不存在、已归档或不属于当前故事。")


def _default_branch_id(conn, story_id: str) -> str | None:
    row = conn.execute(
        "SELECT branch_id FROM story_branches WHERE branch_id = ? AND story_id = ?",
        (default_branch_id(story_id), story_id),
    ).fetchone()
    return str(row[0]) if row is not None else None


def create_reference_library(
    project_name: str,
    title: str,
    *,
    source_kind: str = "reference",
    source_id: str | None = None,
    library_id: str | None = None,
) -> dict[str, Any]:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        result = _create_reference_library(
            conn,
            project_name=project_name,
            title=title,
            source_kind=source_kind,
            source_id=source_id,
            library_id=library_id,
        )
        conn.commit()
        return result


def list_reference_libraries(project_name: str, *, include_archived: bool = False) -> list[dict[str, Any]]:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_reference_libraries_for_project(conn, project_name=project_name)
        result = _list_reference_libraries(conn, project_name=project_name, include_archived=include_archived)
        for library in result:
            library["releases"] = _list_reference_library_releases(conn, str(library["library_id"]))
        conn.commit()
        return result


def load_reference_library(project_name: str, library_id: str) -> dict[str, Any] | None:
    with _with_db(project_name) as conn:
        return _load_reference_library(conn, library_id)


def archive_reference_library(project_name: str, library_id: str) -> bool:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        library = _load_reference_library(conn, library_id)
        if library is None or str(library.get("project_name") or "") != project_name:
            raise ValueError("资料库不存在或不属于当前项目。")
        changed = _archive_reference_library(conn, library_id)
        conn.commit()
        return changed


def create_reference_library_release(
    project_name: str,
    library_id: str,
    *,
    knowledge_ids: Iterable[str] | None = None,
    release_id: str | None = None,
    content_hash: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        result = _create_reference_library_release(
            conn,
            library_id=library_id,
            knowledge_ids=knowledge_ids,
            release_id=release_id,
            content_hash=content_hash,
            manifest=manifest,
        )
        conn.commit()
        return result


def list_reference_library_releases(project_name: str, library_id: str) -> list[dict[str, Any]]:
    with _with_db(project_name) as conn:
        return _list_reference_library_releases(conn, library_id)


def load_reference_library_release(project_name: str, release_id: str) -> dict[str, Any] | None:
    with _with_db(project_name) as conn:
        return _load_reference_library_release(conn, release_id)


def bind_story_library(
    project_name: str,
    story_id: str,
    library_id: str,
    release_id: str,
    *,
    branch_id: str | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        branch_id = branch_id or _default_branch_id(conn, story_id)
        _check_branch(conn, story_id, branch_id, require_active=True)
        state = _load_story_reference_state(conn, story_id=story_id)
        if str(state.get("read_mode") or "legacy") == "legacy":
            raise ValueError("旧故事仍处于兼容读取模式，请先确认完整资料选择后再绑定资料库。")
        result = _bind_story_library(
            conn,
            story_id=story_id,
            library_id=library_id,
            release_id=release_id,
            branch_id=branch_id,
            idempotency_key=idempotency_key,
        )
        conn.commit()
        return result


def list_story_library_bindings(
    project_name: str,
    story_id: str,
    *,
    branch_id: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    with _with_db(project_name) as conn:
        branch_id = branch_id or _default_branch_id(conn, story_id)
        _check_branch(conn, story_id, branch_id)
        return _list_story_library_bindings(conn, story_id=story_id, branch_id=branch_id, include_archived=include_archived)


def load_story_library_binding(project_name: str, binding_id: str) -> dict[str, Any] | None:
    with _with_db(project_name) as conn:
        return _load_story_library_binding(conn, binding_id)


def load_reference_library_release_sources(
    project_name: str,
    release_id: str,
    *,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    with _with_db(project_name) as conn:
        return _load_reference_library_release_sources(conn, release_id=release_id, source_id=source_id)


def unbind_story_library(
    project_name: str,
    binding_id: str,
    *,
    story_id: str | None = None,
    branch_id: str | None = None,
) -> dict[str, Any] | None:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        binding_row = conn.execute(
            "SELECT story_id, branch_id FROM story_library_bindings WHERE binding_id = ?",
            (binding_id,),
        ).fetchone()
        if binding_row is None:
            conn.commit()
            return None
        actual_story_id = str(binding_row[0] or "")
        actual_branch_id = str(binding_row[1] or "").strip()
        if story_id is not None and str(story_id) != actual_story_id:
            raise ValueError("资料绑定不属于当前故事。")
        if branch_id is not None and str(branch_id) != actual_branch_id:
            raise ValueError("资料绑定不属于当前分支。")
        if actual_branch_id:
            _check_branch(conn, actual_story_id, actual_branch_id, require_active=True)
        result = _unbind_story_library(
            conn,
            binding_id,
            expected_story_id=story_id,
            expected_branch_id=branch_id,
        )
        conn.commit()
        return result


def resolve_story_reference_context(
    project_name: str,
    story_id: str,
    *,
    branch_id: str | None = None,
) -> dict[str, Any]:
    with _with_db(project_name) as conn:
        branch_id = branch_id or _default_branch_id(conn, story_id)
        _check_branch(conn, story_id, branch_id)
        return _resolve_story_reference_context(conn, story_id=story_id, branch_id=branch_id)


def list_visible_knowledge_ids(project_name: str, story_id: str, *, branch_id: str | None = None) -> list[str]:
    with _with_db(project_name) as conn:
        branch_id = branch_id or _default_branch_id(conn, story_id)
        _check_branch(conn, story_id, branch_id)
        return _list_visible_knowledge_ids(conn, story_id=story_id, branch_id=branch_id)


def load_legacy_story_reference_status(project_name: str, story_id: str) -> dict[str, Any]:
    """Inspect legacy story knowledge without silently migrating it."""

    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        story = conn.execute(
            "SELECT story_id, name FROM stories WHERE story_id = ? AND deleted_at IS NULL",
            (story_id,),
        ).fetchone()
        if story is None:
            raise ValueError("故事不存在。")
        binding_count = int(conn.execute("SELECT COUNT(*) FROM story_library_bindings WHERE story_id = ? AND status = 'ready'", (story_id,)).fetchone()[0])
        story_knowledge_count = int(conn.execute("SELECT COUNT(*) FROM knowledge_items WHERE story_id = ? AND setting_scope = 'story' AND deleted_at IS NULL", (story_id,)).fetchone()[0])
        linked_count = int(conn.execute(
            """
            SELECT COUNT(*) FROM story_library_item_links AS link
            JOIN story_library_bindings AS binding ON binding.binding_id = link.binding_id
            WHERE binding.story_id = ? AND binding.status = 'ready'
            """,
            (story_id,),
        ).fetchone()[0])
        _ensure_reference_libraries_for_project(conn, project_name=project_name)
        state = _load_story_reference_state(conn, story_id=story_id)
        libraries = _list_reference_libraries(conn, project_name=project_name)
        for library in libraries:
            library["releases"] = _list_reference_library_releases(conn, str(library["library_id"]))
        conn.commit()
        return {
            "story_id": story_id,
            "story_name": str(story["name"]),
            "legacy_read_mode": state["read_mode"] == "legacy",
            "requires_confirmation": state["migration_status"] == "pending",
            "story_knowledge_count": story_knowledge_count,
            "linked_copy_count": linked_count,
            "ready_binding_count": binding_count,
            "state": state,
            "available_libraries": libraries,
        }


def migrate_legacy_story_library(
    project_name: str,
    story_id: str,
    library_id: str,
    release_id: str,
    *,
    branch_id: str | None = None,
) -> dict[str, Any]:
    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        branch_id = branch_id or _default_branch_id(conn, story_id)
        _check_branch(conn, story_id, branch_id, require_active=True)
        result = _migrate_legacy_story_library(
            conn,
            story_id=story_id,
            library_id=library_id,
            release_id=release_id,
            branch_id=branch_id,
        )
        _mark_story_reference_strict(conn, story_id=story_id, binding_id=result.get("binding_id"))
        conn.commit()
        return result


def migrate_legacy_story_libraries(
    project_name: str,
    story_id: str,
    selections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Atomically migrate a complete user-selected public-library set."""

    with _with_db(project_name) as conn:
        conn.execute("BEGIN IMMEDIATE")
        story = conn.execute(
            "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL",
            (story_id,),
        ).fetchone()
        if story is None:
            raise ValueError("故事不存在。")
        default_branch_id = _default_branch_id(conn, story_id)
        if not default_branch_id:
            raise ValueError("故事没有可用的主线分支。")
        _check_branch(conn, story_id, default_branch_id, require_active=True)
        results: list[dict[str, Any]] = []
        for selection in selections:
            if not isinstance(selection, dict):
                raise ValueError("迁移选择格式无效。")
            library_id = str(selection.get("library_id") or "").strip()
            release_id = str(selection.get("release_id") or "").strip()
            if not library_id or not release_id:
                raise ValueError("每个迁移选择都必须包含 library_id 和 release_id。")
            branch_id = str(selection.get("branch_id") or "").strip() or _default_branch_id(conn, story_id)
            _check_branch(conn, story_id, branch_id, require_active=True)
            result = _migrate_legacy_story_library(
                conn,
                story_id=story_id,
                library_id=library_id,
                release_id=release_id,
                branch_id=branch_id,
            )
            results.append(result)
        state = _mark_story_reference_strict(
            conn, story_id=story_id,
            binding_id=results[-1].get("binding_id") if results else None,
        )
        conn.commit()
        return {"story_id": story_id, "bindings": results, "state": state, "legacy_migration": True}
