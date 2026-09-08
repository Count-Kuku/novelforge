"""Unified knowledge-center search, detail, revision, and index state."""

from __future__ import annotations

import difflib

from novelforge.services import memory as _memory_api
from storage.repositories import (
    default_branch_id,
    load_entities,
    load_entity_facts,
    load_entity_relations,
    load_knowledge_graph_rows,
    load_knowledge_center_record_row,
    load_knowledge_index_state_row,
    mark_knowledge_retrieval_state,
    process_knowledge_index_jobs,
    retry_knowledge_index_jobs,
    filter_superseded_visible_items,
    resolve_story_reference_context as _resolve_story_reference_context,
    search_knowledge_center_rows,
    load_timeline,
)


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        import json

        parsed = json.loads(str(value or "{}"))
    except Exception:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _branch_scope(project_name: str, story_id: str, branch_id: str | None, *, writing: bool = False) -> tuple[str, dict]:
    clean_story_id = _memory_api.normalize_story_id(story_id)
    effective_branch_id = str(branch_id or default_branch_id(clean_story_id)).strip()
    branch = _memory_api.load_story_branch(project_name, clean_story_id, effective_branch_id)
    if writing and str(branch.get("status") or "active") == "archived":
        raise ValueError("已归档的世界线只读，不能修改知识。")
    return effective_branch_id, branch


def _knowledge_item_payload(item: dict) -> dict:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else _json_object(item.get("content_json"))
    if not payload:
        payload = {
            key: value for key, value in item.items()
            if key not in {"content_json", "payload", "structured_json", "structured", "quality_json", "quality"}
        }
    return dict(payload)


def _normalize_visible_item(item: dict, *, branch_id: str, checkpoint: bool = False) -> dict:
    result = dict(item)
    payload = _knowledge_item_payload(result)
    knowledge_id = str(result.get("knowledge_id") or result.get("id") or payload.get("knowledge_id") or payload.get("id") or "").strip()
    if not knowledge_id:
        return {}
    result["knowledge_id"] = knowledge_id
    result["id"] = knowledge_id
    result["payload"] = payload
    if result.get("superseded_by") and not payload.get("superseded_by"):
        payload["superseded_by"] = result.get("superseded_by")
    result["story_id"] = str(result.get("story_id") or payload.get("story_id") or "")
    result["setting_scope"] = str(result.get("setting_scope") or payload.get("setting_scope") or "story")
    result["branch_id"] = branch_id
    origin_id = str(result.get("origin_knowledge_id") or payload.get("origin_knowledge_id") or "").strip()
    if origin_id:
        result["origin_knowledge_id"] = origin_id
    if checkpoint:
        result["origin_branch_id"] = str(item.get("branch_id") or payload.get("branch_id") or "")
        result["visible_from_checkpoint"] = True
    return result


def _visible_item_for_id(visible: dict[str, dict], knowledge_id: str) -> dict | None:
    """Resolve a requested parent ID to a branch-local override when present."""

    clean_id = str(knowledge_id or "").strip()
    if not clean_id:
        return None
    direct = visible.get(clean_id)
    if direct is not None:
        return direct
    for item in visible.values():
        if str(item.get("origin_knowledge_id") or "").strip() == clean_id:
            return item
    return None


def _visible_story_items(
    project_name: str,
    story_id: str,
    branch_id: str | None,
    *,
    include_superseded: bool = False,
) -> tuple[str, dict[str, dict]]:
    effective_branch_id, _ = _branch_scope(project_name, story_id, branch_id)
    # resolve_branch_context returns the immutable checkpoint payload for the
    # inherited prefix. It is deliberately read before the SQL query so a
    # first read can establish the default checkpoint for legacy stories.
    branch_context = _memory_api.resolve_branch_context(project_name, story_id, effective_branch_id)
    manifest_items: dict[str, dict] = {}
    for entry in branch_context.get("visible_revision_manifest", []) if isinstance(branch_context, dict) else []:
        if not isinstance(entry, dict) or str(entry.get("item_kind") or "") != "knowledge":
            continue
        item = _normalize_visible_item(entry.get("payload") if isinstance(entry.get("payload"), dict) else {}, branch_id=effective_branch_id, checkpoint=True)
        if item:
            frozen_revision_id = str(entry.get("item_revision_id") or "").strip()
            if frozen_revision_id:
                item["frozen_revision_id"] = frozen_revision_id
                item["revision_id"] = frozen_revision_id
        if item:
            manifest_items[str(item["knowledge_id"])] = item

    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        reference_context = _resolve_story_reference_context(
            conn,
            story_id=_memory_api.normalize_story_id(story_id),
            branch_id=effective_branch_id,
        )
        disabled_ids = {
            str(row[0])
            for row in conn.execute(
                """
                SELECT link.local_knowledge_id
                FROM story_library_item_links AS link
                JOIN story_library_bindings AS binding ON binding.binding_id = link.binding_id
                WHERE binding.story_id = ? AND binding.status <> 'ready'
                  AND link.local_knowledge_id IS NOT NULL
                """,
                (_memory_api.normalize_story_id(story_id),),
            ).fetchall()
        }
    visible: dict[str, dict] = {
        key: value for key, value in manifest_items.items() if key not in disabled_ids
    }
    # Branch-local rows with origin_knowledge_id are immutable checkpoint
    # overrides: replace the inherited parent ID while keeping the local ID
    # available for subsequent edits and search results.
    local_rows = branch_context.get("local_knowledge_payloads", []) if isinstance(branch_context, dict) else []
    for raw in local_rows if isinstance(local_rows, list) else []:
        if not isinstance(raw, dict):
            continue
        raw_status = str(raw.get("status") or "confirmed").strip().lower()
        item = _normalize_visible_item(raw, branch_id=effective_branch_id)
        if not item:
            continue
        origin_id = str(item.get("origin_knowledge_id") or "").strip()
        if origin_id and origin_id in visible:
            visible.pop(origin_id, None)
        if raw_status in {"deleted", "tombstone"}:
            visible.pop(str(item.get("knowledge_id") or ""), None)
            continue
        if str(item.get("knowledge_id") or "") in disabled_ids:
            continue
        visible[str(item["knowledge_id"])] = item
    for raw in reference_context.get("knowledge", []) if isinstance(reference_context, dict) else []:
        item = _normalize_visible_item(raw, branch_id=effective_branch_id)
        if item and str(item["knowledge_id"]) not in disabled_ids:
            # A checkpoint item is authoritative for inherited IDs; local rows
            # fill new facts created after the fork. Main-branch rows written
            # after a checkpoint are allowed to advance that main checkpoint.
            key = str(item["knowledge_id"])
            origin_id = str(item.get("origin_knowledge_id") or "").strip()
            if origin_id and origin_id in visible:
                visible.pop(origin_id, None)
            existing = visible.get(key)
            # The branch projection already contains the current local value
            # plus its frozen entities/edges/evidence. A plain reference row
            # with the same ID must not erase that projection.
            if existing:
                continue
            visible[key] = item
    filtered_items = list(visible.values())
    if not include_superseded:
        filtered_items = filter_superseded_visible_items(filtered_items)
    visible = {
        str(item.get("knowledge_id") or item.get("id") or ""): item
        for item in filtered_items
        if str(item.get("knowledge_id") or item.get("id") or "").strip()
    }
    return effective_branch_id, visible


def assert_story_knowledge_access(
    project_name: str,
    story_id: str,
    branch_id: str | None,
    knowledge_ids: list[str],
    *,
    writing: bool = False,
) -> tuple[str, dict[str, dict]]:
    effective_branch_id, visible = _visible_story_items(project_name, story_id, branch_id)
    requested = [str(value or "").strip() for value in knowledge_ids if str(value or "").strip()]
    missing = [value for value in requested if _visible_item_for_id(visible, value) is None]
    if missing:
        raise ValueError("知识条目不属于当前故事世界线。")
    if writing:
        _branch_scope(project_name, story_id, effective_branch_id, writing=True)
    return effective_branch_id, visible


def assert_story_knowledge_writable(project_name: str, story_id: str, branch_id: str | None, knowledge_id: str) -> tuple[str, dict]:
    effective_branch_id, visible = assert_story_knowledge_access(
        project_name, story_id, branch_id, [knowledge_id], writing=True,
    )
    record = _visible_item_for_id(visible, knowledge_id) or {}
    origin_branch_id = str(record.get("origin_branch_id") or "").strip()
    owner_branch_id = str(record.get("branch_id") or "").strip()
    if origin_branch_id and origin_branch_id != effective_branch_id:
        raise ValueError("当前世界线只能查看继承资料，不能直接修改父线知识。")
    if owner_branch_id and owner_branch_id != effective_branch_id:
        raise ValueError("知识条目不属于当前故事世界线。")
    return effective_branch_id, record


def list_visible_story_knowledge(
    project_name: str,
    story_id: str,
    branch_id: str | None = None,
    *,
    category: str | None = None,
) -> list[dict]:
    _, visible = _visible_story_items(project_name, story_id, branch_id)
    items = list(visible.values())
    clean_category = str(category or "").strip()
    if clean_category:
        items = [item for item in items if str(item.get("category") or item.get("payload", {}).get("category") or "") == clean_category]
    return items


def _source_row_for_knowledge(conn, row: dict, payload: dict):
    source_id = str(row.get("source_id") or payload.get("source_id") or "").strip()
    if not source_id:
        return None
    return conn.execute(
        "SELECT source_id, title, source_type, story_id, metadata_json, active_revision_id "
        "FROM source_documents WHERE source_id = ? AND deleted_at IS NULL",
        (source_id,),
    ).fetchone()


def _promoted_copy_id(
    conn,
    knowledge_id: str,
    payload: dict,
    setting_scope: str,
    promotion_index: dict[str, str] | None = None,
) -> str:
    explicit = str(
        payload.get("promoted_knowledge_id")
        or payload.get("project_knowledge_id")
        or ""
    ).strip()
    if explicit:
        return explicit
    if setting_scope == "project":
        return str(
            payload.get("source_story_knowledge_id")
            or payload.get("promoted_from_knowledge_id")
            or ""
        ).strip()
    if not knowledge_id:
        return ""
    if promotion_index is not None:
        return str(promotion_index.get(knowledge_id) or "").strip()
    row = conn.execute(
        """
        SELECT knowledge_id
        FROM knowledge_items
        WHERE deleted_at IS NULL AND setting_scope = 'project'
          AND (
              json_extract(content_json, '$.source_story_knowledge_id') = ?
              OR json_extract(content_json, '$.promoted_from_knowledge_id') = ?
          )
        ORDER BY updated_at DESC, knowledge_id
        LIMIT 1
        """,
        (knowledge_id, knowledge_id),
    ).fetchone()
    return str(row[0] or "").strip() if row else ""


def _build_promotion_index(conn, source_ids: set[str]) -> dict[str, str]:
    """Resolve page-level promotion links with one bounded project query."""

    clean_ids = sorted({str(value or "").strip() for value in source_ids if str(value or "").strip()})
    if not clean_ids:
        return {}
    placeholders = ",".join("?" for _ in clean_ids)
    rows = conn.execute(
        f"""
        SELECT knowledge_id, content_json
        FROM knowledge_items
        WHERE deleted_at IS NULL AND setting_scope = 'project'
          AND (
              json_extract(content_json, '$.source_story_knowledge_id') IN ({placeholders})
              OR json_extract(content_json, '$.promoted_from_knowledge_id') IN ({placeholders})
          )
        ORDER BY updated_at DESC, knowledge_id
        """,
        (*clean_ids, *clean_ids),
    ).fetchall()
    result: dict[str, str] = {}
    for row in rows:
        payload = _json_object(row["content_json"] if hasattr(row, "keys") else row[1])
        for key in ("source_story_knowledge_id", "promoted_from_knowledge_id"):
            source_id = str(payload.get(key) or "").strip()
            if source_id in clean_ids:
                result.setdefault(source_id, str(row["knowledge_id"] if hasattr(row, "keys") else row[0]).strip())
    return result


def _decorate_knowledge_record(
    conn,
    result: dict,
    *,
    promotion_index: dict[str, str] | None = None,
) -> dict:
    """Add stable ownership/source/promotion fields consumed by search and UI.

    The promotion eligibility helper is shared with the write workflow.  This
    keeps the UI flag conservative: a missing source or fragment origin never
    becomes implicitly shareable merely because a row happens to have a story.
    """

    if not isinstance(result, dict):
        return result
    record_type = str(result.get("record_type") or "").strip()
    if record_type and record_type != "knowledge":
        result.setdefault("can_promote", False)
        return result

    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    knowledge_id = str(result.get("knowledge_id") or result.get("record_id") or payload.get("knowledge_id") or payload.get("id") or "").strip()
    if not knowledge_id:
        result["can_promote"] = False
        return result
    setting_scope = str(result.get("setting_scope") or payload.get("setting_scope") or "").strip().lower()
    story_id = str(result.get("story_id") or payload.get("story_id") or "").strip()
    source = _source_row_for_knowledge(conn, result, payload)
    source_metadata = _json_object(source["metadata_json"] if source is not None else "{}")
    source_origin = str(
        payload.get("source_origin")
        or source_metadata.get("source_origin")
        or source_metadata.get("canonical_url")
        or ""
    ).strip()
    source_type = str(payload.get("source_type") or (source["source_type"] if source is not None else "") or "").strip()
    attachment_id = str(
        payload.get("creative_attachment_id")
        or source_metadata.get("creative_attachment_id")
        or ""
    ).strip()
    batch_id = str(payload.get("batch_id") or source_metadata.get("batch_id") or "").strip()
    source_id = str(result.get("source_id") or payload.get("source_id") or (source["source_id"] if source is not None else "") or "").strip()
    source_segment_id = str(result.get("segment_id") or result.get("source_segment_id") or payload.get("source_segment_id") or payload.get("segment_id") or "").strip()
    promoted_id = _promoted_copy_id(conn, knowledge_id, payload, setting_scope, promotion_index)
    item_for_eligibility = {
        **payload,
        "id": knowledge_id,
        "knowledge_id": knowledge_id,
        "category": result.get("category") or payload.get("category") or "",
        "setting_scope": setting_scope,
        "story_id": story_id,
        "status": result.get("status") or payload.get("status") or "confirmed",
        "source_id": source_id,
        "source_segment_id": source_segment_id,
        "source_origin": source_origin,
        "source_type": source_type,
        "creative_attachment_id": attachment_id,
    }
    eligible = False
    eligibility = {"eligible": False, "reason": "该条目暂不可提升。", "code": "unavailable"}
    live_segment = None
    if source is not None and source_segment_id:
        live_segment = conn.execute(
            """
            SELECT segment_id, source_id, import_status
            FROM source_segments
            WHERE segment_id = ? AND source_id = ? AND deleted_at IS NULL
            """,
            (source_segment_id, source_id),
        ).fetchone()
    if source is not None and live_segment is not None:
        try:
            from novelforge.domain.knowledge_promotion import check_knowledge_promotion_eligibility

            source_for_eligibility = dict(source)
            source_for_eligibility.update(dict(live_segment))
            eligibility = check_knowledge_promotion_eligibility(item_for_eligibility, source=source_for_eligibility)
            eligible = bool(eligibility.get("eligible"))
        except Exception as exc:
            eligibility = {"eligible": False, "reason": str(exc), "code": "eligibility_error"}
    elif source is not None:
        eligibility = {
            "eligible": False,
            "reason": "缺少有效的资料导入片段。",
            "code": "missing_import_source",
        }
    result.update({
        "knowledge_id": knowledge_id,
        "setting_scope": setting_scope,
        "story_id": story_id,
        "source_id": source_id,
        "source_segment_id": source_segment_id,
        "source_title": str(payload.get("source_title") or (source["title"] if source is not None else "") or "").strip(),
        "source_origin": source_origin,
        "source_type": source_type,
        "creative_attachment_id": attachment_id,
        "batch_id": batch_id,
        "promoted_knowledge_id": promoted_id,
        "can_promote": eligible,
        "promotion_block_reason": "" if eligible else str(eligibility.get("reason") or "该条目暂不可提升。"),
    })
    return result


def load_knowledge_graph(
    project_name: str,
    *,
    story_id: str | None = None,
    worldline_id: str | None = None,
    branch_id: str | None = None,
) -> dict:
    """Return the current relationship projection of authoritative knowledge."""

    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    visible: dict[str, dict] | None = None
    effective_branch_id = None
    if story_id is not None:
        effective_branch_id, visible = _visible_story_items(project_name, story_id, branch_id)
        return _snapshot_story_graph(visible)
    elif branch_id:
        raise ValueError("branch_id 必须与 story_id 一起提供。")
    graph_story_id = story_id if story_id is not None else ""
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        entity_ids = None
        if visible is not None:
            entity_ids = [str(item.get("entity_id") or "") for item in visible.values() if str(item.get("entity_id") or "")]
        else:
            # Public project graph must not pick up entity edges belonging to
            # any story merely because their edge has no story discriminator.
            entity_ids = [
                str(entity.get("entity_id") or "")
                for entity in load_entities(conn)
                if str(entity.get("setting_scope") or "project") == "project"
                and not str(entity.get("story_id") or "").strip()
            ]
        return load_knowledge_graph_rows(
            conn, story_id=graph_story_id, worldline_id=worldline_id, entity_ids=entity_ids,
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
    branch_id: str | None = None,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    visible: dict[str, dict] | None = None
    effective_branch_id = None
    if story_id is not None:
        effective_branch_id, visible = _visible_story_items(project_name, story_id, branch_id)
    elif branch_id:
        raise ValueError("branch_id 必须与 story_id 一起提供。")
    search_story_id = story_id if story_id is not None else ""
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
            story_id=search_story_id,
            worldline_id=worldline_id,
            include_archived=include_archived,
            archived_only=archived_only,
            cursor=cursor,
            page_size=page_size,
            record_ids=list(visible) if visible is not None else None,
        )
        # FTS keeps the page query small; decorate each returned knowledge row
        # from the authoritative table so ownership/source fields never rely
        # on a client-side default.
        page_knowledge_ids = {
            str(item.get("record_id") or "").strip()
            for item in result.get("items", [])
            if isinstance(item, dict) and str(item.get("record_type") or "") == "knowledge"
        }
        promotion_index = _build_promotion_index(conn, page_knowledge_ids)
        rows_by_knowledge_id: dict[str, dict] = {}
        if page_knowledge_ids:
            placeholders = ",".join("?" for _ in page_knowledge_ids)
            rows_by_knowledge_id = {
                str(row["knowledge_id"]): dict(row)
                for row in conn.execute(
                    f"SELECT * FROM knowledge_items WHERE knowledge_id IN ({placeholders}) AND deleted_at IS NULL",
                    tuple(sorted(page_knowledge_ids)),
                ).fetchall()
            }
        for item in result.get("items", []):
            if not isinstance(item, dict) or str(item.get("record_type") or "") != "knowledge":
                if isinstance(item, dict):
                    item.setdefault("can_promote", False)
                continue
            row = rows_by_knowledge_id.get(str(item.get("record_id") or ""))
            snapshot = visible.get(str(item.get("record_id") or "")) if visible is not None else None
            if row is None and snapshot is None:
                item["can_promote"] = False
                continue
            if row is not None:
                item.update(row)
                item["payload"] = _json_object(item.get("content_json"))
                item.pop("content_json", None)
                _decorate_knowledge_record(conn, item, promotion_index=promotion_index)
            if snapshot is not None:
                item.update({
                    key: value for key, value in snapshot.items()
                    if key not in {"content_json", "payload"}
                })
                item["payload"] = dict(snapshot.get("payload") or {})
                item["branch_id"] = effective_branch_id
                if snapshot.get("visible_from_checkpoint"):
                    item["can_promote"] = False
            else:
                item.setdefault("can_promote", False)
        conn.commit()
        return result


def load_knowledge_center_record(
    project_name: str,
    record_type: str,
    record_id: str,
    *,
    story_id: str | None = None,
    branch_id: str | None = None,
) -> dict:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    visible: dict[str, dict] | None = None
    effective_branch_id = None
    if story_id is not None:
        effective_branch_id, visible = _visible_story_items(
            project_name, story_id, branch_id, include_superseded=True,
        )
    elif branch_id:
        raise ValueError("branch_id 必须与 story_id 一起提供。")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        result = load_knowledge_center_record_row(conn, record_type, record_id)
        clean_type = str(record_type or "").strip()
        if visible is not None and clean_type == "knowledge":
            snapshot = _visible_item_for_id(visible, record_id)
            if snapshot is None:
                return {}
            if not result:
                result = {
                    "record_type": "knowledge",
                    "record_id": str(record_id),
                    "status": "confirmed",
                    "archived": False,
                }
            else:
                _decorate_knowledge_record(conn, result)
            result.update({key: value for key, value in snapshot.items() if key not in {"content_json", "payload"}})
            result["payload"] = dict(snapshot.get("payload") or {})
            result["branch_id"] = effective_branch_id
            result["record_type"] = "knowledge"
            result["record_id"] = str(snapshot.get("knowledge_id") or record_id)
            result["knowledge_id"] = str(snapshot.get("knowledge_id") or record_id)
        elif visible is not None and clean_type == "pending":
            if not result or str(result.get("story_id") or "") != str(story_id) or str(result.get("branch_id") or "") != str(effective_branch_id):
                return {}
        elif visible is not None and clean_type == "source":
            if not result:
                return {}
            source_id = str(result.get("source_id") or "")
            segment_id = str(result.get("segment_id") or result.get("record_id") or "")
            if not any(
                source_id and source_id == str(item.get("source_id") or "")
                or segment_id and segment_id in {str(item.get("segment_id") or ""), str(item.get("source_segment_id") or "")}
                for item in visible.values()
            ):
                return {}
        elif visible is None and clean_type in {"knowledge", "pending"}:
            if result and (str(result.get("setting_scope") or "") == "story" or str(result.get("story_id") or "")):
                return {}
        if result and clean_type == "knowledge" and not (visible is not None):
            _decorate_knowledge_record(conn, result)
        elif result and clean_type != "knowledge":
            result.setdefault("can_promote", False)
        return result


def load_visible_story_knowledge_revisions(
    project_name: str,
    knowledge_id: str,
    *,
    story_id: str,
    branch_id: str | None = None,
) -> list[dict]:
    """Return frozen checkpoint history for inherited rows, never parent future revisions."""

    record = load_knowledge_center_record(
        project_name, "knowledge", knowledge_id, story_id=story_id, branch_id=branch_id,
    )
    if not record:
        return []
    if record.get("visible_from_checkpoint"):
        snapshot = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        revision_id = str(record.get("frozen_revision_id") or record.get("revision_id") or f"checkpoint:{knowledge_id}")
        return [{
            "revision_id": revision_id,
            "revision_no": 1,
            "change_type": "checkpoint",
            "reason": "分叉时冻结的知识基线",
            "snapshot": dict(snapshot),
            "created_at": record.get("updated_at") or record.get("created_at") or "",
            "frozen": True,
        }]
    from novelforge.services.memory import load_knowledge_revisions

    resolved_id = str(record.get("knowledge_id") or knowledge_id)
    return load_knowledge_revisions(project_name, resolved_id)


def load_visible_story_knowledge_evidence(
    project_name: str,
    knowledge_id: str,
    *,
    story_id: str,
    branch_id: str | None = None,
) -> list[dict]:
    """Read inherited evidence from its checkpoint payload, not live parent rows."""

    record = load_knowledge_center_record(
        project_name, "knowledge", knowledge_id, story_id=story_id, branch_id=branch_id,
    )
    if not record:
        return []
    if record.get("visible_from_checkpoint"):
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        raw_evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        result: list[dict] = []
        for index, item in enumerate(raw_evidence, start=1):
            normalized = dict(item) if isinstance(item, dict) else {"quote": str(item or "")}
            normalized.setdefault("evidence_id", f"checkpoint_evidence:{knowledge_id}:{index}")
            normalized["frozen"] = True
            result.append(normalized)
        return result
    from novelforge.services.memory import load_knowledge_evidence

    resolved_id = str(record.get("knowledge_id") or knowledge_id)
    return load_knowledge_evidence(project_name, resolved_id)


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
    story_id: str | None = None,
    branch_id: str | None = None,
) -> dict:
    from novelforge.services.memory import create_story_knowledge_override, load_knowledge_revisions, update_confirmed_knowledge_item_record

    requested_record = load_knowledge_center_record(
        project_name, "knowledge", knowledge_id, story_id=story_id, branch_id=branch_id,
    ) if story_id is not None else {}
    effective_branch_id = str(branch_id or default_branch_id(story_id)) if story_id is not None else ""
    inherited = bool(
        story_id is not None
        and requested_record.get("visible_from_checkpoint")
        and str(requested_record.get("origin_branch_id") or "")
        and str(requested_record.get("origin_branch_id") or "") != effective_branch_id
    )
    if inherited:
        revisions = load_visible_story_knowledge_revisions(
            project_name, knowledge_id, story_id=story_id, branch_id=effective_branch_id,
        )
        target = next((item for item in revisions if str(item.get("revision_id") or "") == str(revision_id or "")), None)
        snapshot = target.get("snapshot") if isinstance(target, dict) and isinstance(target.get("snapshot"), dict) else None
        if not snapshot:
            raise ValueError("要恢复的知识修订不存在。")
        override = create_story_knowledge_override(
            project_name,
            requested_record,
            {
                **snapshot,
                "category": str(snapshot.get("category") or requested_record.get("category") or ""),
                "revision_reason": reason,
                "restored_from_revision_id": revision_id,
            },
            story_id=story_id,
            branch_id=effective_branch_id,
            reason=reason,
        )
        override_id = str(override.get("knowledge_id") or override.get("id") or "")
        return {"knowledge_id": override_id, "origin_knowledge_id": str(knowledge_id), "revision_id": revision_id, "restored": True, "created_override": True}

    if story_id is not None:
        effective_branch_id, current = assert_story_knowledge_writable(project_name, story_id, branch_id, knowledge_id)
    else:
        effective_branch_id, current = None, load_knowledge_center_record(project_name, "knowledge", knowledge_id)
    revisions = load_knowledge_revisions(project_name, knowledge_id)
    target = next(
        (item for item in revisions if str(item.get("revision_id") or "") == str(revision_id or "")),
        None,
    )
    if not target or not isinstance(target.get("snapshot"), dict):
        raise ValueError("要恢复的知识修订不存在。")
    snapshot = dict(target["snapshot"])
    target_category = str(snapshot.get("category") or "").strip()
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
    if story_id is not None:
        snapshot.update({
            "story_id": str(story_id),
            "branch_id": effective_branch_id,
            "setting_scope": "story",
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


def _snapshot_entity_value(item: dict, key: str, default=None):
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    if item.get(key) is not None:
        return item.get(key)
    return payload.get(key, default)


def _snapshot_entity_redirects(visible: dict[str, dict]) -> dict[str, str]:
    """Unify inherited and local graph nodes only through explicit origins."""
    origins: dict[str, str] = {}
    candidates: list[tuple[int, str]] = []
    for item in visible.values():
        inherited = bool(item.get("visible_from_checkpoint") and item.get("origin_branch_id") != item.get("branch_id"))
        priority = 0 if inherited else 1
        entity_id = str(_snapshot_entity_value(item, "entity_id") or "")
        origin = str(_snapshot_entity_value(item, "origin_entity_id") or _snapshot_entity_value(item, "target_origin_entity_id") or "")
        if entity_id:
            candidates.append((priority, entity_id))
            if origin and origin != entity_id:
                origins[entity_id] = origin
        relations = _snapshot_entity_value(item, "entity_relations", [])
        for relation in relations if isinstance(relations, list) else []:
            if not isinstance(relation, dict):
                continue
            for endpoint in ("source", "target"):
                node_id = str(relation.get(f"{endpoint}_node_id") or "")
                origin_id = str(_snapshot_entity_value(item, f"{endpoint}_origin_entity_id") or "")
                if node_id and origin_id:
                    candidates.append((priority, node_id))
                    if node_id != origin_id:
                        origins[node_id] = origin_id

    def root(entity_id: str) -> str:
        visited: set[str] = set()
        while entity_id in origins and entity_id not in visited:
            visited.add(entity_id)
            entity_id = origins[entity_id]
        return entity_id

    preferred: dict[str, tuple[int, str]] = {}
    for priority, entity_id in candidates:
        key = root(entity_id)
        preferred[key] = max(preferred.get(key, (-1, "")), (priority, entity_id))
    return {
        entity_id: preferred[root(entity_id)][1]
        for entity_id in {*origins, *origins.values(), *(entity_id for _, entity_id in candidates)}
        if root(entity_id) in preferred
    }


def _snapshot_entity_cards(
    visible: dict[str, dict],
    *,
    entity_type: str | None = None,
    setting_types: tuple[str, ...] = (),
    max_cards: int,
) -> list[dict]:
    """Build entity cards from the branch snapshot, never live parent rows."""
    grouped: dict[str, list[dict]] = {}
    identities: dict[str, dict] = {}
    redirects = _snapshot_entity_redirects(visible)
    for item in visible.values():
        original_entity_id = str(_snapshot_entity_value(item, "entity_id") or "").strip()
        entity_id = redirects.get(original_entity_id, original_entity_id)
        if not entity_id:
            continue
        entity = _snapshot_entity_value(item, "entity", {})
        entity = dict(entity) if isinstance(entity, dict) else {}
        item_entity_type = str(_snapshot_entity_value(item, "entity_type") or entity.get("entity_type") or "").strip()
        if entity_type and item_entity_type != entity_type:
            continue
        if setting_types and item_entity_type not in setting_types:
            continue
        grouped.setdefault(entity_id, []).append(item)
        identity = {
            "entity_id": entity_id,
            "entity_type": item_entity_type or str(entity.get("entity_type") or ""),
            "canonical_name": str(entity.get("canonical_name") or _snapshot_entity_value(item, "canonical_name") or _snapshot_entity_value(item, "name") or ""),
            "summary": str(entity.get("summary") or ""),
            "importance": entity.get("importance") or _snapshot_entity_value(item, "importance") or 0.5,
            "setting_scope": str(entity.get("setting_scope") or _snapshot_entity_value(item, "setting_scope") or "story"),
            "story_id": str(entity.get("story_id") or _snapshot_entity_value(item, "story_id") or ""),
            "version_scope": str(entity.get("version_scope") or _snapshot_entity_value(item, "version_scope") or ""),
            "worldline_id": str(entity.get("worldline_id") or _snapshot_entity_value(item, "worldline_id") or ""),
        }
        if entity_id not in identities or entity_id == original_entity_id:
            identities[entity_id] = identity

    graph = _snapshot_story_graph(visible)
    names = {node["node_id"]: node["name"] for node in graph["nodes"]}
    types = {node["node_id"]: node["node_type"] for node in graph["nodes"]}

    def relations_for(entity_id: str) -> list[dict]:
        return [edge for edge in graph["edges"] if entity_id in {edge["source_node_id"], edge["target_node_id"]}]

    cards: list[dict] = []
    for entity_id, facts in grouped.items():
        identity = identities[entity_id]
        summaries = [
            str(_snapshot_entity_value(fact, "summary") or "").strip()
            for fact in facts
            if str(_snapshot_entity_value(fact, "summary") or "").strip()
        ]
        profile: dict[str, str] = {}
        aliases: list[str] = []
        source_ids: list[str] = []
        source_chips: list[dict] = []
        for fact in facts:
            fact_key = str(_snapshot_entity_value(fact, "fact_key") or "").strip()
            summary = str(_snapshot_entity_value(fact, "summary") or "").strip()
            if fact_key and summary:
                profile[fact_key] = summary
            raw_aliases = _snapshot_entity_value(fact, "entity_aliases", [])
            if isinstance(raw_aliases, list):
                aliases.extend(str(alias) for alias in raw_aliases if str(alias).strip())
            fact_id = str(_snapshot_entity_value(fact, "knowledge_id") or "").strip()
            if fact_id:
                source_ids.append(fact_id)
            title = str(_snapshot_entity_value(fact, "source_title") or "").strip()
            origin = str(_snapshot_entity_value(fact, "source_origin") or "").strip()
            segment = str(_snapshot_entity_value(fact, "source_segment_id") or "").strip()
            if title or origin or segment:
                source_chips.append({
                    "title": title or "未命名来源",
                    "origin": origin,
                    "segment_id": segment,
                    "knowledge_id": fact_id,
                })
        aliases = list(dict.fromkeys(aliases))
        source_chips = list({
            (str(chip["title"]), str(chip["origin"]), str(chip["segment_id"])): chip
            for chip in source_chips
        }.values())
        relationships: list[str] = []
        abilities: list[str] = []
        items: list[str] = []
        events: list[str] = []
        affiliations: list[str] = []
        related: list[str] = []
        for relation in relations_for(entity_id):
            source_id = str(relation.get("source_node_id") or "")
            target_id = str(relation.get("target_node_id") or "")
            outgoing = source_id == entity_id or (not source_id and bool(relation.get("outgoing")))
            other_id = target_id if outgoing else source_id
            other_type = types.get(other_id, str(relation.get("other_type") or "entity"))
            other_name = names.get(other_id, str(relation.get("other_name") or other_id))
            relation_type = str(relation.get("relation_type") or "关联")
            if other_id:
                related.append(f"{other_name}（{relation_type}）")
            if not outgoing and other_type == "ability":
                abilities.append(other_name)
            elif not outgoing and other_type == "item":
                items.append(other_name)
            elif not outgoing and other_type == "event":
                events.append(other_name)
            elif outgoing and other_type == "organization":
                affiliations.append(other_name)
            else:
                relationships.append(f"{other_name}（{relation_type}）")
        source_ids = list(dict.fromkeys(source_ids))
        if setting_types:
            cards.append({
                "id": entity_id,
                "entity_type": "setting",
                "setting_type": str(_snapshot_entity_value(facts[0], "category") or identity["entity_type"]),
                "name": identity["canonical_name"],
                "summary": identity["summary"] or (summaries[0] if summaries else ""),
                "profile": {}, "rules": summaries, "timeline": [], "related_entities": related,
                "conflicts": [], "evidence": [], "sources": source_chips, "confidence": 0.7,
                "importance": identity["importance"], "canon_status": "unknown",
                "scope": identity["setting_scope"], "setting_scope": identity["setting_scope"],
                "story_id": identity["story_id"], "version_scope": identity["version_scope"],
                "worldline_id": identity["worldline_id"], "worldline_label": "",
                "source_knowledge_ids": source_ids,
                "primary_knowledge_id": source_ids[0] if source_ids else "",
                "tags": ["设定实体卡", "entity_setting"], "status": "entity_card",
            })
        else:
            cards.append({
                "id": entity_id, "entity_type": "character", "name": identity["canonical_name"],
                "aliases": aliases, "summary": identity["summary"] or (summaries[0] if summaries else ""),
                "profile": profile, "relationships": relationships, "abilities": abilities,
                "items": items, "abilities_and_items": abilities + items, "dialogue_style": [],
                "constraints": [], "timeline": events, "events": events, "evidence": [],
                "sources": source_chips, "confidence": 0.7, "importance": identity["importance"],
                "canon_status": "unknown", "scope": identity["setting_scope"],
                "setting_scope": identity["setting_scope"], "story_id": identity["story_id"],
                "version_scope": identity["version_scope"], "worldline_id": identity["worldline_id"],
                "worldline_label": "", "source_knowledge_ids": source_ids,
                "primary_knowledge_id": source_ids[0] if source_ids else "",
                "affiliations": affiliations, "tags": ["角色实体卡", "entity_character"],
                "status": "entity_card",
            })
    return cards[:max_cards]


def _snapshot_story_graph(visible: dict[str, dict]) -> dict:
    names: dict[str, dict] = {}
    edges: list[dict] = []
    seen_edges: set[str] = set()
    redirects = _snapshot_entity_redirects(visible)

    def add_node(entity: dict, fallback: dict | None = None) -> None:
        fallback = fallback or {}
        original_id = str(entity.get("entity_id") or _snapshot_entity_value(fallback, "entity_id") or "").strip()
        entity_id = redirects.get(original_id, original_id)
        if not entity_id:
            return
        node = {
            "node_id": entity_id,
            "name": str(entity.get("display_name") or entity.get("canonical_name") or _snapshot_entity_value(fallback, "name") or entity_id),
            "node_type": str(entity.get("entity_type") or _snapshot_entity_value(fallback, "entity_type") or "entity"),
        }
        if entity_id not in names or entity_id == original_id:
            names[entity_id] = node

    for item in visible.values():
        entity = _snapshot_entity_value(item, "entity", {})
        entity = dict(entity) if isinstance(entity, dict) else {}
        add_node(entity, item)
        related = _snapshot_entity_value(item, "related_entities", [])
        for endpoint in related if isinstance(related, list) else []:
            if isinstance(endpoint, dict):
                add_node(endpoint)
        raw_relations = _snapshot_entity_value(item, "entity_relations", [])
        for raw in raw_relations if isinstance(raw_relations, list) else []:
            if not isinstance(raw, dict):
                continue
            source_id = str(raw.get("source_node_id") or "").strip()
            target_id = str(raw.get("target_node_id") or "").strip()
            source_id = redirects.get(source_id, source_id)
            target_id = redirects.get(target_id, target_id)
            if not source_id or not target_id:
                continue
            edge_id = str(raw.get("edge_id") or f"{source_id}:{target_id}:{raw.get('relation_type')}")
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            edges.append({
                **raw,
                "edge_id": edge_id,
                "source_node_id": source_id,
                "target_node_id": target_id,
                "source_name": names.get(source_id, {}).get("name") or source_id,
                "target_name": names.get(target_id, {}).get("name") or target_id,
                "source_type": names.get(source_id, {}).get("node_type") or "entity",
                "target_type": names.get(target_id, {}).get("node_type") or "entity",
                "knowledge_id": str(_snapshot_entity_value(item, "knowledge_id") or ""),
                "knowledge_item": item.get("payload") if isinstance(item.get("payload"), dict) else {},
            })
    for edge in edges:
        edge["source_name"] = names.get(edge["source_node_id"], {}).get("name") or edge["source_node_id"]
        edge["target_name"] = names.get(edge["target_node_id"], {}).get("name") or edge["target_node_id"]
        edge["source_type"] = names.get(edge["source_node_id"], {}).get("node_type") or "entity"
        edge["target_type"] = names.get(edge["target_node_id"], {}).get("node_type") or "entity"
    return {"nodes": list(names.values()), "edges": edges}


def load_character_entity_cards(
    project_name: str,
    *,
    max_characters: int = 80,
    story_id: str | None = None,
    branch_id: str | None = None,
) -> list[dict]:
    """Entity-centric character cards read from the entities table (not name-based merge).

    Returns the same card shape as ``build_character_entity_cards`` so callers are
    unchanged, but the source of truth is now the entity master + its facts + edges.
    """
    if _memory_api._project_db_marked_unavailable(project_name):
        return []
    if story_id is not None:
        _, visible = _visible_story_items(project_name, story_id, branch_id)
        return _snapshot_entity_cards(visible, entity_type="character", max_cards=max_characters)
    visible_ids: set[str] | None = None
    visible_entity_ids: set[str] | None = None
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            entities = load_entities(conn, entity_type="character", story_id=story_id)
            if story_id is None:
                # Project view is the public knowledge view.  ``story_id=None``
                # in the repository means "project plus every story", so make
                # the scope explicit before building cards.
                entities = [
                    entity for entity in entities
                    if str(entity.get("setting_scope") or "project") == "project"
                    and not str(entity.get("story_id") or "").strip()
                ]
    except Exception:
        return []
    project_entity_ids = {str(entity.get("entity_id") or "") for entity in entities}
    cards: list[dict] = []
    for entity in entities:
        if visible_entity_ids is not None and str(entity.get("entity_id") or "") not in visible_entity_ids:
            continue
        entity_id = entity["entity_id"]
        try:
            with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
                facts = load_entity_facts(conn, entity_id)
                relations = load_entity_relations(conn, entity_id)
        except Exception:
            facts, relations = [], []
        if visible_ids is not None:
            facts = [fact for fact in facts if str(fact.get("knowledge_id") or "") in visible_ids]
            if not facts:
                continue
            if visible_entity_ids is not None:
                relations = [relation for relation in relations if str(relation.get("other_entity_id") or "") in visible_entity_ids]
            elif story_id is None:
                relations = [relation for relation in relations if str(relation.get("other_entity_id") or "") in project_entity_ids]
        # Group facts by fact_key into a profile; summary from entity master.
        profile: dict[str, str] = {}
        fact_summaries: list[str] = []
        for fact in facts:
            summary = str(fact.get("summary") or "").strip()
            if not summary:
                continue
            fact_summaries.append(summary)
            key = fact.get("fact_key")
            if key:
                profile[key] = summary
        # Classify edges by relation semantics. Incoming edges reference this
        # entity from the other side (ability -> character, item -> character,
        # event -> character); outgoing edges go from this entity to others
        # (character -> organization).
        abilities: list[str] = []
        items: list[str] = []
        events: list[str] = []
        affiliations: list[str] = []
        relationships: list[str] = []
        for r in relations:
            name = r["other_name"]
            otype = r["other_type"]
            rel = r["relation_type"]
            if not r["outgoing"] and otype == "ability":
                abilities.append(name)
            elif not r["outgoing"] and otype == "item":
                items.append(name)
            elif not r["outgoing"] and otype == "event":
                events.append(name)
            elif r["outgoing"] and otype == "organization":
                affiliations.append(name)
            else:
                relationships.append(f"{name}（{rel}）")
        # Source chips from the owning facts (source_title / source_origin).
        sources: list[dict] = []
        seen_sources: set[tuple[str, str, str]] = set()
        for fact in facts:
            payload = fact.get("content_json") if isinstance(fact.get("content_json"), dict) else {}
            key = (
                str(payload.get("source_title") or "").strip(),
                str(payload.get("source_origin") or "").strip(),
                str(payload.get("source_segment_id") or "").strip(),
            )
            if not any(key) or key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "title": key[0] or "未命名来源",
                "origin": key[1],
                "segment_id": key[2],
                "knowledge_id": str(fact.get("knowledge_id") or ""),
            })
        cards.append({
            "id": entity_id,
            "entity_type": "character",
            "name": entity["canonical_name"],
            "aliases": [],
            "summary": entity.get("summary") or (fact_summaries[0] if fact_summaries else ""),
            "profile": profile,
            "relationships": relationships,
            "abilities": abilities,
            "items": items,
            "abilities_and_items": abilities + items,
            "dialogue_style": [],
            "constraints": [],
            "timeline": events,
            "events": events,
            "evidence": [],
            "sources": sources,
            "confidence": 0.7,
            "importance": entity.get("importance") or 0.5,
            "canon_status": "unknown",
            "scope": entity.get("setting_scope") or "project",
            "setting_scope": entity.get("setting_scope") or "project",
            "story_id": entity.get("story_id") or "",
            "version_scope": entity.get("version_scope") or "",
            "worldline_id": entity.get("worldline_id") or "",
            "worldline_label": "",
            "source_knowledge_ids": [f.get("knowledge_id") for f in facts if f.get("knowledge_id")],
            "primary_knowledge_id": facts[0].get("knowledge_id") if facts else "",
            "affiliations": affiliations,
            "tags": ["角色实体卡", "entity_character"],
            "status": "entity_card",
        })
    return cards[:max_characters]


def load_setting_entity_cards(
    project_name: str,
    *,
    max_cards: int = 120,
    story_id: str | None = None,
    branch_id: str | None = None,
) -> list[dict]:
    """Entity-centric setting cards (organizations/locations/items/abilities/world_rules)."""
    if _memory_api._project_db_marked_unavailable(project_name):
        return []
    setting_types = ("organization", "location", "item", "ability", "world_rule")
    if story_id is not None:
        _, visible = _visible_story_items(project_name, story_id, branch_id)
        return _snapshot_entity_cards(visible, setting_types=setting_types, max_cards=max_cards)
    visible_ids: set[str] | None = None
    visible_entity_ids: set[str] | None = None
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            entities = [e for e in load_entities(conn, story_id=story_id) if e["entity_type"] in setting_types]
            if story_id is None:
                entities = [
                    entity for entity in entities
                    if str(entity.get("setting_scope") or "project") == "project"
                    and not str(entity.get("story_id") or "").strip()
                ]
    except Exception:
        return []
    project_entity_ids = {str(entity.get("entity_id") or "") for entity in entities}
    cards: list[dict] = []
    for entity in entities:
        if visible_entity_ids is not None and str(entity.get("entity_id") or "") not in visible_entity_ids:
            continue
        entity_id = entity["entity_id"]
        try:
            with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
                facts = load_entity_facts(conn, entity_id)
                relations = load_entity_relations(conn, entity_id)
        except Exception:
            facts, relations = [], []
        if visible_ids is not None:
            facts = [fact for fact in facts if str(fact.get("knowledge_id") or "") in visible_ids]
            if not facts:
                continue
            if visible_entity_ids is not None:
                relations = [relation for relation in relations if str(relation.get("other_entity_id") or "") in visible_entity_ids]
            elif story_id is None:
                relations = [relation for relation in relations if str(relation.get("other_entity_id") or "") in project_entity_ids]
        fact_summaries = [str(f.get("summary") or "").strip() for f in facts if str(f.get("summary") or "").strip()]
        related = [
            f"{r['other_name']}（{r['relation_type']}）"
            for r in relations
        ]
        # setting_type mirrors the legacy category name (world_rules, not world_rule).
        setting_type = facts[0].get("category") if facts else entity["entity_type"]
        sources: list[dict] = []
        seen_sources: set[tuple[str, str, str]] = set()
        for fact in facts:
            payload = fact.get("content_json") if isinstance(fact.get("content_json"), dict) else {}
            key = (
                str(payload.get("source_title") or "").strip(),
                str(payload.get("source_origin") or "").strip(),
                str(payload.get("source_segment_id") or "").strip(),
            )
            if not any(key) or key in seen_sources:
                continue
            seen_sources.add(key)
            sources.append({
                "title": key[0] or "未命名来源",
                "origin": key[1],
                "segment_id": key[2],
                "knowledge_id": str(fact.get("knowledge_id") or ""),
            })
        cards.append({
            "id": entity_id,
            "entity_type": "setting",
            "setting_type": setting_type,
            "name": entity["canonical_name"],
            "summary": entity.get("summary") or (fact_summaries[0] if fact_summaries else ""),
            "profile": {},
            "rules": fact_summaries,
            "timeline": [],
            "related_entities": related,
            "conflicts": [],
            "evidence": [],
            "sources": sources,
            "confidence": 0.7,
            "importance": entity.get("importance") or 0.5,
            "canon_status": "unknown",
            "scope": entity.get("setting_scope") or "project",
            "setting_scope": entity.get("setting_scope") or "project",
            "story_id": entity.get("story_id") or "",
            "version_scope": entity.get("version_scope") or "",
            "worldline_id": entity.get("worldline_id") or "",
            "worldline_label": "",
            "source_knowledge_ids": [f.get("knowledge_id") for f in facts if f.get("knowledge_id")],
            "primary_knowledge_id": facts[0].get("knowledge_id") if facts else "",
            "tags": ["设定实体卡", "entity_setting"],
            "status": "entity_card",
        })
    return cards[:max_cards]
