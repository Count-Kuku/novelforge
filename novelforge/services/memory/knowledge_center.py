"""Unified knowledge-center search, detail, revision, and index state."""

from __future__ import annotations

import difflib

from novelforge.services import memory as _memory_api
from storage.repositories import (
    load_knowledge_graph_rows,
    load_knowledge_center_record_row,
    load_knowledge_index_state_row,
    mark_knowledge_retrieval_state,
    process_knowledge_index_jobs,
    retry_knowledge_index_jobs,
    search_knowledge_center_rows,
)


def load_knowledge_graph(
    project_name: str,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
) -> dict:
    """Return the current relationship projection of authoritative knowledge."""

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        return load_knowledge_graph_rows(
            conn, story_id=story_id, worldline_id=worldline_id,
        )


def search_knowledge_center(
    project_name: str,
    *,
    query: str = "",
    record_types: list[str] | None = None,
    categories: list[str] | None = None,
    story_id: str | None = None,
    worldline_id: str | None = None,
    include_archived: bool = False,
    archived_only: bool = False,
    cursor: str = "",
    page_size: int = 40,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        # FTS projection is small and local; process queued row-level changes
        # before searching so a committed edit is discoverable immediately.
        batch = process_knowledge_index_jobs(conn, limit=100)
        if batch.get("failed_total"):
            # Failed jobs stay failed and visible until the user explicitly
            # retries them; searching must not create an implicit retry loop.
            pass
        result = search_knowledge_center_rows(
            conn,
            query=query,
            record_types=record_types,
            categories=categories,
            story_id=story_id,
            worldline_id=worldline_id,
            include_archived=include_archived,
            archived_only=archived_only,
            cursor=cursor,
            page_size=page_size,
        )
        conn.commit()
        return result


def load_knowledge_center_record(
    project_name: str,
    record_type: str,
    record_id: str,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        return load_knowledge_center_record_row(conn, record_type, record_id)


def load_knowledge_center_index_state(project_name: str) -> dict:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        load_knowledge_index_state_row,
        "knowledge center index state",
    )
    return result if isinstance(result, dict) else {}


def process_knowledge_center_index(project_name: str, *, limit: int = 1000) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        result = process_knowledge_index_jobs(conn, limit=limit)
        conn.commit()
        return result


def retry_knowledge_center_index(project_name: str) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        retried = retry_knowledge_index_jobs(conn)
        conn.commit()
    from novelforge.workflows.knowledge_index_dispatcher import wake_knowledge_index_dispatcher

    wake_knowledge_index_dispatcher(project_name)
    return {"retried": retried, "state": load_knowledge_center_index_state(project_name)}


def set_knowledge_retrieval_index_state(
    project_name: str,
    status: str,
    *,
    indexed_revision: int | None = None,
    error_text: str = "",
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        result = mark_knowledge_retrieval_state(
            conn, status, indexed_revision=indexed_revision, error_text=error_text,
        )
        conn.commit()
        return result


def knowledge_revision_diff(current: dict, revision: dict) -> str:
    import json

    before = revision.get("snapshot") if isinstance(revision.get("snapshot"), dict) else {}
    after = current if isinstance(current, dict) else {}
    return "\n".join(difflib.unified_diff(
        json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True).splitlines(),
        json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True).splitlines(),
        fromfile=f"修订 {revision.get('revision_no', '-')}",
        tofile="当前版本",
        lineterm="",
    ))


def restore_knowledge_revision(
    project_name: str,
    knowledge_id: str,
    revision_id: str,
    *,
    reason: str = "从历史修订恢复",
) -> dict:
    from novelforge.services.memory import load_knowledge_revisions, update_confirmed_knowledge_item_record

    revisions = load_knowledge_revisions(project_name, knowledge_id)
    target = next(
        (item for item in revisions if str(item.get("revision_id") or "") == str(revision_id or "")),
        None,
    )
    if not target or not isinstance(target.get("snapshot"), dict):
        raise ValueError("要恢复的知识修订不存在。")
    snapshot = dict(target["snapshot"])
    target_category = str(snapshot.get("category") or "").strip()
    current = load_knowledge_center_record(project_name, "knowledge", knowledge_id)
    current_category = str(current.get("category") or "").strip()
    if not target_category or not current_category:
        raise ValueError("历史修订缺少知识分类。")
    snapshot.update({
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": target_category,
        "revision_reason": reason,
        "restored_from_revision_id": revision_id,
    })
    if not update_confirmed_knowledge_item_record(
        project_name, current_category, knowledge_id, snapshot, target_category=target_category,
    ):
        raise RuntimeError("知识修订恢复失败。")
    return {"knowledge_id": knowledge_id, "revision_id": revision_id, "restored": True}


def restore_archived_knowledge_item(
    project_name: str,
    knowledge_id: str,
    *,
    reason: str = "从归档恢复",
) -> dict:
    from novelforge.services.memory import upsert_knowledge_category_item_record

    record = load_knowledge_center_record(project_name, "knowledge", knowledge_id)
    if not record or not record.get("archived"):
        raise ValueError("要恢复的归档知识不存在。")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    category = str(record.get("category") or payload.get("category") or "").strip()
    if not category:
        raise ValueError("归档知识缺少分类。")
    restored = upsert_knowledge_category_item_record(project_name, category, {
        **payload,
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": category,
        "status": "confirmed",
        "revision_reason": reason,
        "restored_from_archive": True,
    })
    return {"knowledge_id": knowledge_id, "restored": True, "item": restored}
