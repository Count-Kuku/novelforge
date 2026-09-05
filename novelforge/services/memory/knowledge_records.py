"""Implementation slice for the memory facade: confirmed knowledge record CRUD."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

def upsert_knowledge_category_item_record(project_name: str, category: str, item: dict) -> dict:
    """Atomically upsert one knowledge item without replacing concurrent peers."""

    if category not in _memory_api.KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        saved, items = _memory_api.upsert_knowledge_category_item(conn, category, item)
        conn.commit()
    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return saved


def delete_knowledge_category_item_record(project_name: str, category: str, item_id: str) -> bool:
    """Atomically delete one knowledge item without replacing concurrent peers."""

    if category not in _memory_api.KNOWLEDGE_CATEGORIES:
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        deleted, items = _memory_api.delete_knowledge_category_item(conn, category, item_id)
        conn.commit()
    if deleted:
        _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return deleted


def update_confirmed_knowledge_item_record(
    project_name: str,
    original_category: str,
    item_id: str,
    updated_item: dict,
    *,
    target_category: str | None = None,
    delete_only: bool = False,
) -> bool:
    """Atomically update, move, or delete one confirmed knowledge item.

    A category move changes the source and target categories inside one
    ``BEGIN IMMEDIATE`` transaction.  This prevents a failure while writing
    the target category from committing the source-category deletion.
    """

    source_category = str(original_category or "").strip()
    destination_category = str(target_category or source_category).strip()
    clean_item_id = str(item_id or "").strip()
    if (
        source_category not in _memory_api.KNOWLEDGE_CATEGORIES
        or destination_category not in _memory_api.KNOWLEDGE_CATEGORIES
        or not clean_item_id
    ):
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    snapshots: dict[str, list[dict]] = {}
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        source_items = _memory_api.load_knowledge_category_rows(conn, source_category)
        original = next(
            (
                item
                for item in source_items
                if str(item.get("id") or item.get("knowledge_id") or "").strip() == clean_item_id
            ),
            None,
        )
        if original is None:
            conn.rollback()
            return False

        if delete_only:
            deleted, source_after = _memory_api.delete_knowledge_category_item(
                conn,
                source_category,
                clean_item_id,
            )
            if not deleted:
                conn.rollback()
                return False
            snapshots[source_category] = source_after
        else:
            updates = updated_item if isinstance(updated_item, dict) else {}
            normalized = {
                **original,
                **updates,
                "id": clean_item_id,
                "knowledge_id": clean_item_id,
                "category": destination_category,
                "status": str(updates.get("status") or original.get("status") or "confirmed"),
            }
            if destination_category == source_category:
                _, source_after = _memory_api.upsert_knowledge_category_item(
                    conn,
                    source_category,
                    normalized,
                )
                snapshots[source_category] = source_after
            else:
                deleted, source_after = _memory_api.delete_knowledge_category_item(
                    conn,
                    source_category,
                    clean_item_id,
                )
                if not deleted:
                    conn.rollback()
                    return False
                _, target_after = _memory_api.upsert_knowledge_category_item(
                    conn,
                    destination_category,
                    normalized,
                )
                snapshots[source_category] = source_after
                snapshots[destination_category] = target_after
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return True


def merge_confirmed_knowledge_item_records(
    project_name: str,
    category: str,
    item_ids: list[str],
    merged_item: dict,
) -> bool:
    """Atomically replace confirmed knowledge items with one merged item."""

    clean_category = str(category or "").strip()
    clean_item_ids = list(dict.fromkeys(
        str(item_id or "").strip()
        for item_id in item_ids
        if str(item_id or "").strip()
    ))
    if clean_category not in _memory_api.KNOWLEDGE_CATEGORIES or len(clean_item_ids) < 2:
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _memory_api.load_knowledge_category_rows(conn, clean_category)
        current_by_id = {
            str(item.get("id") or item.get("knowledge_id") or "").strip(): item
            for item in current
        }
        if any(item_id not in current_by_id for item_id in clean_item_ids):
            conn.rollback()
            return False

        normalized = dict(merged_item or {})
        merged_id = str(
            normalized.get("id")
            or normalized.get("knowledge_id")
            or clean_item_ids[0]
        ).strip()
        if not merged_id or (merged_id in current_by_id and merged_id not in clean_item_ids):
            conn.rollback()
            return False
        normalized.update({
            "id": merged_id,
            "knowledge_id": merged_id,
            "category": clean_category,
            "status": str(normalized.get("status") or "confirmed"),
        })
        normalized.setdefault("created_at", current_by_id[clean_item_ids[0]].get("created_at"))

        category_after = current
        for selected_id in clean_item_ids:
            deleted, category_after = _memory_api.delete_knowledge_category_item(
                conn,
                clean_category,
                selected_id,
            )
            if not deleted:
                conn.rollback()
                return False
        _, category_after = _memory_api.upsert_knowledge_category_item(
            conn,
            clean_category,
            normalized,
        )
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return True


def delete_confirmed_knowledge_item_records(
    project_name: str,
    category: str,
    item_ids: list[str],
) -> int:
    """Atomically delete explicitly identified confirmed knowledge items."""

    clean_category = str(category or "").strip()
    clean_item_ids = list(dict.fromkeys(
        str(item_id or "").strip()
        for item_id in item_ids
        if str(item_id or "").strip()
    ))
    if clean_category not in _memory_api.KNOWLEDGE_CATEGORIES or not clean_item_ids:
        return 0
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    deleted_count = 0
    category_after: list[dict] = []
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _memory_api.load_knowledge_category_rows(conn, clean_category)
        active_ids = {
            str(item.get("id") or item.get("knowledge_id") or "").strip()
            for item in current
        }
        selected_ids = [item_id for item_id in clean_item_ids if item_id in active_ids]
        if not selected_ids:
            conn.rollback()
            return 0
        category_after = current
        for selected_id in selected_ids:
            deleted, category_after = _memory_api.delete_knowledge_category_item(
                conn,
                clean_category,
                selected_id,
            )
            if deleted:
                deleted_count += 1
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return deleted_count
