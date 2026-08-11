"""Implementation slice for the memory facade: knowledge."""

from __future__ import annotations

from novelforge.services import memory as _memory_api
from novelforge.domain.knowledge_types import normalize_typed_knowledge_item
from storage.repositories.knowledge import (
    load_knowledge_evidence_rows,
    load_knowledge_revision_rows,
    summarize_knowledge_storage_health,
)

def knowledge_dir_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def knowledge_category_path(project_name: str, category: str) -> _memory_api.Path:
    safe_category = str(category or "").strip()
    if safe_category not in _memory_api.KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    return knowledge_dir_path(project_name) / f"{safe_category}.json"


def knowledge_entities_dir_path(project_name: str) -> _memory_api.Path:
    path = knowledge_dir_path(project_name) / "entities"
    path.mkdir(parents=True, exist_ok=True)
    return path


def character_entities_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "characters.json"


def setting_entities_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "settings.json"


def entity_aliases_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "aliases.json"


def extraction_plan_templates_path(project_name: str) -> _memory_api.Path:
    return knowledge_entities_dir_path(project_name) / "extraction_plans.json"


def pending_knowledge_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "pending.json"


def auto_review_runs_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "auto_review_runs.json"


def auto_review_policy_path(project_name: str) -> _memory_api.Path:
    return knowledge_dir_path(project_name) / "auto_review_policy.json"


DEFAULT_AUTO_REVIEW_POLICY = {
    "min_confidence": 0.45,
    "min_evidence_strength": 0.35,
    "grade_a_confidence": 0.75,
    "grade_a_evidence_strength": 0.65,
    "allow_grade_b_auto_confirm": True,
    "require_evidence": True,
    "manual_review_categories": ["constraints"],
}


def _load_json_list(path: _memory_api.Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def load_knowledge_category(project_name: str, category: str) -> list[dict]:
    db_items = _memory_api._load_knowledge_category_from_db_best_effort(project_name, category)
    if db_items is not None:
        return db_items
    json_items = _load_json_list(knowledge_category_path(project_name, category))
    if db_items == [] and json_items:
        _memory_api._sync_knowledge_category_to_db_best_effort(project_name, category, json_items)
    return json_items


def save_knowledge_category(project_name: str, category: str, items: list[dict]):
    path = knowledge_category_path(project_name, category)
    normalized = [normalize_typed_knowledge_item(item, category) for item in items if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_knowledge_category_to_db_best_effort(project_name, category, normalized)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_knowledge_base(project_name: str) -> dict[str, list[dict]]:
    return {
        category: load_knowledge_category(project_name, category)
        for category in _memory_api.KNOWLEDGE_CATEGORIES
    }


def load_knowledge_revisions(project_name: str, knowledge_id: str) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_knowledge_revision_rows(conn, knowledge_id),
        "knowledge revisions",
    )
    return result if isinstance(result, list) else []


def load_knowledge_evidence(project_name: str, knowledge_id: str) -> list[dict]:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: load_knowledge_evidence_rows(conn, knowledge_id),
        "knowledge evidence",
    )
    return result if isinstance(result, list) else []


def load_knowledge_storage_health(project_name: str) -> dict:
    result = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        summarize_knowledge_storage_health,
        "knowledge storage health",
    )
    return result if isinstance(result, dict) else {}


def load_character_entities(project_name: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="character_entities",
        logical_key="characters",
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    return _load_json_list(character_entities_path(project_name))


def save_character_entities(project_name: str, items: list[dict]):
    path = character_entities_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="character_entities",
        logical_key="characters",
        title="Character Entities",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_setting_entities(project_name: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="setting_entities",
        logical_key="settings",
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    return _load_json_list(setting_entities_path(project_name))


def save_setting_entities(project_name: str, items: list[dict]):
    path = setting_entities_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="setting_entities",
        logical_key="settings",
        title="Setting Entities",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_entity_aliases(project_name: str) -> list[dict]:
    db_items = _memory_api._load_entity_aliases_from_db_best_effort(project_name)
    if db_items is not None:
        return db_items
    json_items = _load_json_list(entity_aliases_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_entity_aliases_to_db_best_effort(project_name, json_items)
    return json_items


def save_entity_aliases(project_name: str, items: list[dict]):
    path = entity_aliases_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_entity_aliases_to_db_best_effort(project_name, normalized)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_extraction_plan_templates(project_name: str) -> list[dict]:
    db_items = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="extraction_plan_templates",
        logical_key="templates",
    )
    if isinstance(db_items, list):
        return [item for item in db_items if isinstance(item, dict)]
    return _load_json_list(extraction_plan_templates_path(project_name))


def save_extraction_plan_templates(project_name: str, items: list[dict]):
    path = extraction_plan_templates_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="extraction_plan_templates",
        logical_key="templates",
        title="Extraction Plan Templates",
        payload=normalized,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_pending_knowledge_items(project_name: str) -> list[dict]:
    db_items = _memory_api._load_pending_knowledge_from_db_best_effort(project_name)
    if db_items is not None:
        return db_items
    json_items = _load_json_list(pending_knowledge_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_pending_knowledge_to_db_best_effort(project_name, json_items)
    return json_items


def save_pending_knowledge_items(project_name: str, items: list[dict]):
    path = pending_knowledge_path(project_name)
    normalized = [
        normalize_typed_knowledge_item(item, str(item.get("category") or ""))
        for item in items
        if isinstance(item, dict)
    ]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_pending_knowledge_to_db_best_effort(project_name, normalized)


def load_auto_review_runs(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_auto_review_run_rows, "auto review runs")
    if db_items is not None:
        return db_items
    json_items = _load_json_list(auto_review_runs_path(project_name))
    if db_items == [] and json_items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_auto_review_runs(conn, json_items),
        )
    return json_items


def save_auto_review_runs(project_name: str, runs: list[dict]):
    path = auto_review_runs_path(project_name)
    normalized = [item for item in runs if isinstance(item, dict)]
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_auto_review_runs(conn, normalized),
    )


def normalize_auto_review_policy(policy: dict | None) -> dict:
    raw = policy if isinstance(policy, dict) else {}
    normalized = dict(DEFAULT_AUTO_REVIEW_POLICY)
    for key in ["min_confidence", "min_evidence_strength", "grade_a_confidence", "grade_a_evidence_strength"]:
        try:
            value = float(raw.get(key, normalized[key]))
        except (TypeError, ValueError):
            value = float(normalized[key])
        normalized[key] = max(0.0, min(1.0, value))
    normalized["allow_grade_b_auto_confirm"] = bool(raw.get("allow_grade_b_auto_confirm", normalized["allow_grade_b_auto_confirm"]))
    normalized["require_evidence"] = bool(raw.get("require_evidence", normalized["require_evidence"]))
    categories = raw.get("manual_review_categories", normalized["manual_review_categories"])
    if not isinstance(categories, list):
        categories = normalized["manual_review_categories"]
    normalized["manual_review_categories"] = [
        str(category)
        for category in categories
        if str(category) in _memory_api.KNOWLEDGE_CATEGORIES
    ]
    return normalized


def load_auto_review_policy(project_name: str) -> dict:
    db_policy = _memory_api._load_runtime_from_db_best_effort(project_name, _memory_api.load_auto_review_policy_row, "auto review policy")
    if db_policy is not None:
        return normalize_auto_review_policy(db_policy)
    path = auto_review_policy_path(project_name)
    if not path.exists():
        return dict(DEFAULT_AUTO_REVIEW_POLICY)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    normalized = normalize_auto_review_policy(raw)
    if db_policy == [] or db_policy == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_auto_review_policy(conn, normalized),
        )
    return normalized


def save_auto_review_policy(project_name: str, policy: dict) -> dict:
    normalized = normalize_auto_review_policy(policy)
    path = auto_review_policy_path(project_name)
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_auto_review_policy(conn, normalized),
    )
    return normalized


def append_auto_review_run(project_name: str, run: dict) -> dict:
    runs = load_auto_review_runs(project_name)
    normalized = dict(run or {})
    normalized["run_id"] = normalized.get("run_id") or f"auto_review_{_memory_api.uuid4().hex}"
    normalized["created_at"] = normalized.get("created_at") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    normalized["status"] = normalized.get("status") or "active"
    runs.append(normalized)
    save_auto_review_runs(project_name, runs[-200:])
    return normalized


def queue_pending_knowledge_items(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    replace_pending_ids: list[str] | None = None,
) -> int:
    queued_at = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    normalized_items: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        name = str(item.get("name") or "").strip()
        if category not in _memory_api.KNOWLEDGE_CATEGORIES or not name:
            continue
        normalized = normalize_typed_knowledge_item(item, category)
        pending_id = str(normalized.get("pending_id") or f"pending_{_memory_api.uuid4().hex}")
        normalized["pending_id"] = pending_id
        normalized["category"] = category
        normalized["name"] = name
        normalized["scope"] = scope
        normalized["authority"] = authority
        normalized["source_title"] = source_title or normalized.get("source_title", "")
        normalized["source_origin"] = source_origin
        normalized["version_scope"] = normalized.get("version_scope") or ("canon" if scope == "canon" else "project_main")
        normalized["worldline_id"] = normalized.get("worldline_id") or "main"
        normalized["worldline_label"] = normalized.get("worldline_label") or "本项目主线"
        normalized["status"] = "pending"
        normalized["queued_at"] = queued_at
        normalized["updated_at"] = queued_at
        normalized_items.append(normalized)
    if not normalized_items:
        return 0
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        added_count, pending = _memory_api.upsert_pending_knowledge_items(conn, normalized_items)
        incoming_ids = {
            str(item.get("pending_id") or "")
            for item in normalized_items
            if str(item.get("pending_id") or "")
        }
        replacement_ids = {
            str(item)
            for item in (replace_pending_ids or [])
            if str(item)
        } - incoming_ids
        if replacement_ids:
            _, pending = _memory_api.delete_pending_knowledge_items(conn, replacement_ids)
        conn.commit()
    _memory_api._write_json_mirror(pending_knowledge_path(project_name), pending)
    if not _memory_api._write_json_mirrors_enabled():
        _memory_api._delete_pending_mirrors(_memory_api._take_project_pending_mirror_deletions(project_name))
    return len(incoming_ids) if replace_pending_ids is not None else added_count


def discard_pending_knowledge_items(project_name: str, pending_ids: list[str]) -> int:
    id_set = {str(item) for item in pending_ids}
    if not id_set:
        return 0
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        removed_count, remaining = _memory_api.delete_pending_knowledge_items(conn, id_set)
        conn.commit()
    if removed_count:
        _memory_api._write_json_mirror(pending_knowledge_path(project_name), remaining)
        if not _memory_api._write_json_mirrors_enabled():
            _memory_api._delete_pending_mirrors(_memory_api._take_project_pending_mirror_deletions(project_name))
    return removed_count


def confirm_pending_knowledge_items(project_name: str, pending_ids: list[str]) -> int:
    result = confirm_pending_knowledge_items_with_records(project_name, pending_ids)
    return int(result.get("saved_count", 0))


def _append_knowledge_items_in_transaction(
    conn,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    status: str = "confirmed",
    confirmation_metadata: dict | None = None,
) -> tuple[int, list[dict], dict[str, list[dict]]]:
    """Append knowledge rows while the caller holds a project write lock."""

    grouped: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        if category not in _memory_api.KNOWLEDGE_CATEGORIES:
            continue
        grouped.setdefault(category, []).append(item)

    saved_count = 0
    saved_records: list[dict] = []
    category_snapshots: dict[str, list[dict]] = {}
    protected_metadata_keys = {"id", "knowledge_id", "category", "pending_id", "queued_at"}
    for category, category_items in grouped.items():
        existing = _memory_api.load_knowledge_category_rows(conn, category)
        used_ids = {
            str(item.get("id") or item.get("knowledge_id") or "").strip()
            for item in existing
            if str(item.get("id") or item.get("knowledge_id") or "").strip()
        }
        next_index = len(existing) + 1
        for item in category_items:
            normalized = dict(item)
            source_pending_id = str(normalized.get("pending_id") or "")
            normalized.pop("pending_id", None)
            normalized.pop("queued_at", None)
            normalized.setdefault("name", "")
            if not str(normalized.get("name", "")).strip():
                continue

            requested_id = str(normalized.get("id") or normalized.get("knowledge_id") or "").strip()
            if not requested_id or requested_id in used_ids:
                while True:
                    requested_id = _make_knowledge_id(category, next_index)
                    next_index += 1
                    if requested_id not in used_ids:
                        break
            normalized["id"] = requested_id
            normalized.pop("knowledge_id", None)
            used_ids.add(requested_id)
            normalized["category"] = category
            normalized = normalize_typed_knowledge_item(normalized, category)
            normalized["scope"] = scope
            normalized["authority"] = authority
            normalized["source_title"] = source_title or normalized.get("source_title", "")
            normalized["source_origin"] = source_origin
            normalized["version_scope"] = normalized.get("version_scope") or (
                "canon" if scope == "canon" else "project_main"
            )
            normalized["worldline_id"] = normalized.get("worldline_id") or "main"
            normalized["worldline_label"] = normalized.get("worldline_label") or "本项目主线"
            normalized["status"] = status
            if confirmation_metadata:
                normalized.update({
                    str(key): value
                    for key, value in confirmation_metadata.items()
                    if str(key).strip() and str(key) not in protected_metadata_keys
                })
            if source_pending_id:
                normalized["source_pending_id"] = source_pending_id
            existing.append(normalized)
            saved_records.append({
                "pending_id": source_pending_id,
                "category": category,
                "knowledge_id": requested_id,
                "name": normalized.get("name", ""),
                "source_title": normalized.get("source_title", ""),
                "source_origin": normalized.get("source_origin", ""),
            })
            saved_count += 1
        _memory_api.sync_knowledge_category(conn, category, existing)
        category_snapshots[category] = existing
    return saved_count, saved_records, category_snapshots


def _refresh_project_json_mirror(project_name: str, path: _memory_api.Path, payload) -> None:
    try:
        _memory_api._write_json_mirror(path, payload)
        if not _memory_api._write_json_mirrors_enabled():
            _memory_api._delete_pending_mirrors(_memory_api._take_project_pending_mirror_deletions(project_name))
    except OSError as exc:
        _memory_api.logging.getLogger("novelforge.storage").warning(
            "SQLite commit succeeded, but JSON mirror refresh failed for %s: %s",
            path,
            exc,
        )


def _refresh_knowledge_retrieval_best_effort(project_name: str) -> None:
    try:
        _memory_api.sync_project_retrieval_assets(project_name)
    except Exception as exc:
        _memory_api.logging.getLogger("novelforge.retrieval").warning(
            "Knowledge commit succeeded, but retrieval rebuild failed for %s: %s",
            project_name,
            exc,
        )


def confirm_pending_knowledge_items_with_records(
    project_name: str,
    pending_ids: list[str],
    *,
    confirmation_metadata: dict | None = None,
    discard_pending_ids: list[str] | None = None,
    discard_snapshot_metadata: dict[str, dict] | None = None,
    audit_run: dict | None = None,
) -> dict:
    id_set = {str(item) for item in pending_ids if str(item)}
    discard_id_set = {
        str(item)
        for item in (discard_pending_ids or [])
        if str(item)
    }
    if not id_set and not discard_id_set and not audit_run:
        return {
            "saved_count": 0,
            "confirmed_records": [],
            "pending_snapshots": [],
            "discarded_snapshots": [],
            "skipped_pending_ids": [],
            "audit_run": {},
        }
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        pending = _memory_api.load_pending_knowledge_rows(conn)
        selected = [item for item in pending if str(item.get("pending_id", "")) in id_set]

        saved_count = 0
        confirmed_records: list[dict] = []
        category_snapshots: dict[str, list[dict]] = {}
        grouped: dict[tuple[str, str, str, str], list[dict]] = {}
        for item in selected:
            key = (
                str(item.get("scope") or "reference"),
                str(item.get("authority") or "curated"),
                str(item.get("source_title") or ""),
                str(item.get("source_origin") or ""),
            )
            grouped.setdefault(key, []).append(item)
        for (scope, authority, source_title, source_origin), items in grouped.items():
            count, records, snapshots = _append_knowledge_items_in_transaction(
                conn,
                items,
                scope=scope,
                authority=authority,
                source_title=source_title,
                source_origin=source_origin,
                confirmation_metadata=confirmation_metadata,
            )
            saved_count += count
            confirmed_records.extend(records)
            category_snapshots.update(snapshots)
        confirmed_pending_ids = {
            str(record.get("pending_id") or "")
            for record in confirmed_records
            if str(record.get("pending_id") or "")
        }
        confirmed_selected = [
            item
            for item in selected
            if str(item.get("pending_id") or "") in confirmed_pending_ids
        ]
        skipped_pending_ids = sorted(
            str(item.get("pending_id") or "")
            for item in selected
            if str(item.get("pending_id") or "") not in confirmed_pending_ids
        )
        discard_metadata = discard_snapshot_metadata or {}
        discarded_snapshots: list[dict] = []
        discarded_pending_ids: set[str] = set()
        for item in pending:
            pending_id = str(item.get("pending_id") or "")
            if pending_id not in discard_id_set or pending_id in confirmed_pending_ids:
                continue
            snapshot = dict(item)
            metadata = discard_metadata.get(pending_id, {})
            if isinstance(metadata, dict):
                snapshot.update(metadata)
            discarded_snapshots.append(snapshot)
            discarded_pending_ids.add(pending_id)
        removed_pending_ids = confirmed_pending_ids | discarded_pending_ids
        remaining = [
            item
            for item in pending
            if str(item.get("pending_id") or "") not in removed_pending_ids
        ]
        if removed_pending_ids:
            _memory_api.sync_pending_knowledge(conn, remaining)

        audit_record: dict = {}
        if audit_run:
            audit_record = dict(audit_run)
            audit_record["run_id"] = str(audit_record.get("run_id") or f"auto_review_{_memory_api.uuid4().hex}")
            audit_record["created_at"] = str(
                audit_record.get("created_at") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
            )
            audit_record["status"] = str(audit_record.get("status") or "active")
            audit_record["confirmed_ids"] = sorted(confirmed_pending_ids)
            audit_record["confirmed_records"] = confirmed_records
            audit_record["pending_snapshots"] = [
                *[dict(item) for item in confirmed_selected],
                *discarded_snapshots,
            ]
            audit_record["saved_count"] = saved_count
            archived_snapshots = [
                item
                for item in discarded_snapshots
                if item.get("pending_batch_action") == "archive"
            ]
            manual_review_snapshots = [
                item
                for item in discarded_snapshots
                if item.get("pending_batch_action") == "manual_review"
            ]
            if discard_id_set:
                audit_record["archived_snapshots"] = archived_snapshots
                audit_record["manual_review_snapshots"] = manual_review_snapshots
                audit_record["archived_ids"] = sorted(
                    str(item.get("pending_id") or "")
                    for item in archived_snapshots
                    if str(item.get("pending_id") or "")
                )
                audit_record["manual_review_ids"] = sorted(
                    str(item.get("pending_id") or "")
                    for item in manual_review_snapshots
                    if str(item.get("pending_id") or "")
                )
                audit_record["blocked_ids"] = list(audit_record["manual_review_ids"])
            batch_summary = audit_record.get("batch_summary")
            if isinstance(batch_summary, dict):
                audit_record["batch_summary"] = {
                    **batch_summary,
                    "confirmed": len(confirmed_pending_ids),
                    "archived": len(archived_snapshots),
                    "manual_review": len(manual_review_snapshots),
                }
            if skipped_pending_ids:
                blocked_ids = {
                    str(item)
                    for item in audit_record.get("blocked_ids", [])
                    if str(item)
                }
                blocked_ids.update(skipped_pending_ids)
                audit_record["blocked_ids"] = sorted(blocked_ids)
                blocked_reasons = dict(audit_record.get("blocked_reasons") or {})
                for pending_id in skipped_pending_ids:
                    blocked_reasons.setdefault(pending_id, "未生成有效的正式知识，已保留在待确认队列")
                audit_record["blocked_reasons"] = blocked_reasons
            _memory_api.sync_auto_review_runs(conn, [audit_record])
        conn.commit()

    for category, items in category_snapshots.items():
        _refresh_project_json_mirror(project_name, knowledge_category_path(project_name, category), items)
    if removed_pending_ids:
        _refresh_project_json_mirror(project_name, pending_knowledge_path(project_name), remaining)
    if audit_record:
        _refresh_project_json_mirror(
            project_name,
            auto_review_runs_path(project_name),
            load_auto_review_runs(project_name),
        )
    if saved_count:
        _refresh_knowledge_retrieval_best_effort(project_name)
    return {
        "saved_count": saved_count,
        "confirmed_records": confirmed_records,
        "pending_snapshots": [dict(item) for item in confirmed_selected],
        "discarded_snapshots": discarded_snapshots,
        "skipped_pending_ids": skipped_pending_ids,
        "audit_run": audit_record,
    }


def _make_knowledge_id(category: str, index: int) -> str:
    return f"{category}_{index:04d}"


def append_knowledge_items(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    status: str = "confirmed",
) -> int:
    saved_count, _ = append_knowledge_items_with_records(
        project_name,
        items,
        scope=scope,
        authority=authority,
        source_title=source_title,
        source_origin=source_origin,
        status=status,
    )
    return saved_count


def append_knowledge_items_with_records(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    status: str = "confirmed",
    confirmation_metadata: dict | None = None,
) -> tuple[int, list[dict]]:
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        saved_count, saved_records, category_snapshots = _append_knowledge_items_in_transaction(
            conn,
            items,
            scope=scope,
            authority=authority,
            source_title=source_title,
            source_origin=source_origin,
            status=status,
            confirmation_metadata=confirmation_metadata,
        )
        conn.commit()
    for category, category_items in category_snapshots.items():
        _refresh_project_json_mirror(
            project_name,
            knowledge_category_path(project_name, category),
            category_items,
        )
    if saved_count:
        _refresh_knowledge_retrieval_best_effort(project_name)
    return saved_count, saved_records


def rollback_auto_review_run(project_name: str, run_id: str) -> dict:
    target_run_id = str(run_id or "").strip()
    if not target_run_id:
        return {"success": False, "message": "缺少自动审核记录 ID。", "removed_count": 0, "restored_count": 0}

    runs = load_auto_review_runs(project_name)
    run_index = next((index for index, item in enumerate(runs) if str(item.get("run_id") or "") == target_run_id), -1)
    if run_index < 0:
        return {"success": False, "message": "未找到自动审核记录。", "removed_count": 0, "restored_count": 0}

    run = dict(runs[run_index])
    if str(run.get("status") or "") == "rolled_back":
        return {"success": False, "message": "该自动审核记录已经回退过。", "removed_count": 0, "restored_count": 0}

    confirmed_records = run.get("confirmed_records", []) if isinstance(run.get("confirmed_records", []), list) else []
    removed_count = 0
    records_by_category: dict[str, set[str]] = {}
    for record in confirmed_records:
        if not isinstance(record, dict):
            continue
        category = str(record.get("category") or "")
        knowledge_id = str(record.get("knowledge_id") or "")
        if category in _memory_api.KNOWLEDGE_CATEGORIES and knowledge_id:
            records_by_category.setdefault(category, set()).add(knowledge_id)

    for category, id_set in records_by_category.items():
        existing = load_knowledge_category(project_name, category)
        remaining = [item for item in existing if str(item.get("id") or "") not in id_set]
        removed_count += len(existing) - len(remaining)
        if len(remaining) != len(existing):
            save_knowledge_category(project_name, category, remaining)

    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(item.get("pending_id") or "") for item in pending}
    restored_count = 0
    restored_at = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    for snapshot in run.get("pending_snapshots", []) if isinstance(run.get("pending_snapshots", []), list) else []:
        if not isinstance(snapshot, dict):
            continue
        restored = dict(snapshot)
        pending_id = str(restored.get("pending_id") or "")
        if not pending_id:
            restored["pending_id"] = f"pending_rollback_{_memory_api.uuid4().hex}"
            pending_id = str(restored["pending_id"])
        if pending_id in existing_pending_ids:
            continue
        restored["status"] = "pending"
        restored["rollback_from_auto_review_run_id"] = target_run_id
        restored["rolled_back_at"] = restored_at
        pending.append(restored)
        existing_pending_ids.add(pending_id)
        restored_count += 1
    if restored_count:
        save_pending_knowledge_items(project_name, pending)

    run["status"] = "rolled_back"
    run["rolled_back_at"] = restored_at
    run["rollback_result"] = {
        "removed_count": removed_count,
        "restored_count": restored_count,
    }
    runs[run_index] = run
    save_auto_review_runs(project_name, runs)
    _memory_api.sync_project_retrieval_assets(project_name)
    return {
        "success": True,
        "message": f"已回退自动审核记录：删除 {removed_count} 条正式知识，恢复 {restored_count} 条待确认知识。",
        "removed_count": removed_count,
        "restored_count": restored_count,
        "run": run,
    }


def restore_auto_review_snapshots_to_pending(
    project_name: str,
    run_id: str,
    pending_ids: list[str],
    *,
    snapshot_field: str = "manual_review_snapshots",
) -> dict:
    target_run_id = str(run_id or "").strip()
    requested_ids = [str(item or "").strip() for item in pending_ids if str(item or "").strip()]
    if not target_run_id or not requested_ids:
        return {"success": False, "message": "缺少处理记录或待恢复条目。", "restored_count": 0}

    runs = load_auto_review_runs(project_name)
    run_index = next((index for index, item in enumerate(runs) if str(item.get("run_id") or "") == target_run_id), -1)
    if run_index < 0:
        return {"success": False, "message": "未找到处理记录。", "restored_count": 0}

    run = dict(runs[run_index])
    if str(run.get("status") or "") == "rolled_back":
        return {"success": False, "message": "该处理记录已经整批回退，不能重复恢复。", "restored_count": 0}

    snapshots = run.get(snapshot_field, []) if isinstance(run.get(snapshot_field, []), list) else []
    snapshot_by_id = {
        str(snapshot.get("pending_id") or ""): snapshot
        for snapshot in snapshots
        if isinstance(snapshot, dict) and str(snapshot.get("pending_id") or "")
    }
    restored_before = set(
        str(item or "")
        for item in run.get("restored_pending_ids", [])
        if str(item or "").strip()
    )

    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(item.get("pending_id") or "") for item in pending if isinstance(item, dict)}
    restored_count = 0
    skipped_ids: list[str] = []
    restored_ids: list[str] = []
    restored_at = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()

    for pending_id in requested_ids:
        snapshot = snapshot_by_id.get(pending_id)
        if not snapshot or pending_id in existing_pending_ids or pending_id in restored_before:
            skipped_ids.append(pending_id)
            continue
        restored = dict(snapshot)
        restored["status"] = "pending"
        restored["restored_from_auto_review_run_id"] = target_run_id
        restored["restored_from_snapshot_field"] = snapshot_field
        restored["restored_at"] = restored_at
        pending.append(restored)
        existing_pending_ids.add(pending_id)
        restored_before.add(pending_id)
        restored_ids.append(pending_id)
        restored_count += 1

    if restored_count:
        save_pending_knowledge_items(project_name, pending)

    run["restored_pending_ids"] = sorted(restored_before)
    restore_events = run.get("restore_events", [])
    if not isinstance(restore_events, list):
        restore_events = []
    restore_events.append({
        "restored_at": restored_at,
        "snapshot_field": snapshot_field,
        "requested_ids": requested_ids,
        "restored_ids": restored_ids,
        "skipped_ids": skipped_ids,
    })
    run["restore_events"] = restore_events[-50:]
    runs[run_index] = run
    save_auto_review_runs(project_name, runs)

    return {
        "success": True,
        "message": f"已恢复 {restored_count} 条到待确认队列，跳过 {len(skipped_ids)} 条。",
        "restored_count": restored_count,
        "skipped_count": len(skipped_ids),
        "restored_ids": restored_ids,
        "skipped_ids": skipped_ids,
    }


def return_confirmed_knowledge_item_to_pending(
    project_name: str,
    category: str,
    knowledge_id: str,
    *,
    reason: str = "",
) -> dict:
    target_category = str(category or "").strip()
    target_id = str(knowledge_id or "").strip()
    if target_category not in _memory_api.KNOWLEDGE_CATEGORIES or not target_id:
        return {"success": False, "message": "缺少有效的知识分类或知识 ID。", "pending_id": ""}

    items = load_knowledge_category(project_name, target_category)
    item_index = next((index for index, item in enumerate(items) if str(item.get("id") or "") == target_id), -1)
    if item_index < 0:
        return {"success": False, "message": "未找到要退回的正式知识。", "pending_id": ""}

    item = dict(items[item_index])
    remaining = [entry for index, entry in enumerate(items) if index != item_index]
    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(entry.get("pending_id") or "") for entry in pending}
    pending_id = str(item.get("source_pending_id") or "")
    if not pending_id or pending_id in existing_pending_ids:
        pending_id = f"pending_returned_{_memory_api.uuid4().hex}"

    restored = dict(item)
    restored.pop("id", None)
    restored.pop("auto_reviewed_at", None)
    restored["pending_id"] = pending_id
    restored["category"] = target_category
    restored["status"] = "pending"
    restored["returned_from_knowledge_id"] = target_id
    restored["returned_from_auto_review_run_id"] = item.get("auto_review_run_id", "")
    restored["return_reason"] = reason
    restored["returned_at"] = _memory_api.datetime.now(_memory_api.timezone.utc).isoformat()
    pending.append(restored)

    save_knowledge_category(project_name, target_category, remaining)
    save_pending_knowledge_items(project_name, pending)

    run_id = str(item.get("auto_review_run_id") or "")
    if run_id:
        runs = load_auto_review_runs(project_name)
        for run in runs:
            if str(run.get("run_id") or "") != run_id:
                continue
            returned = run.get("returned_records", [])
            if not isinstance(returned, list):
                returned = []
            returned.append({
                "category": target_category,
                "knowledge_id": target_id,
                "pending_id": pending_id,
                "name": item.get("name", ""),
                "returned_at": restored["returned_at"],
                "reason": reason,
            })
            run["returned_records"] = returned
            break
        save_auto_review_runs(project_name, runs)

    _memory_api.sync_project_retrieval_assets(project_name)
    return {
        "success": True,
        "message": f"已将 {item.get('name', target_id)} 退回待确认队列。",
        "pending_id": pending_id,
    }


def load_story_rules(project_name: str, story_id: str) -> dict:
    db_rules = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_rules_payload(conn, "story", story_id),
        "story rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    path = _memory_api._story_rules_overrides_path(project_name, story_id)
    if not path.exists():
        return _memory_api.normalize_rules(None)
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        normalized = _memory_api.normalize_rules(raw)
    except Exception:
        return _memory_api.normalize_rules(None)
    if db_rules == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
        )
    return normalized


def save_story_rules(project_name: str, story_id: str, rules: dict):
    path = _memory_api._story_rules_overrides_path(project_name, story_id)
    normalized = _memory_api.normalize_rules(rules)
    if all(len(v) == 0 for v in normalized.values()):
        if path.exists():
            path.unlink()
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
        )
        return
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_rules_payload(conn, "story", normalized, story_id),
    )


def load_global_rules() -> dict:
    db_rules = _memory_api._load_global_from_db_best_effort(
        lambda conn: _memory_api.load_rules_payload(conn, "global"),
        "global rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    _memory_api.GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _memory_api.GLOBAL_RULES_PATH.exists():
        rules = _memory_api.normalize_rules(None)
        save_global_rules(rules)
        return rules

    try:
        rules = _memory_api.json.loads(_memory_api.GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
    except (_memory_api.json.JSONDecodeError, OSError):
        rules = _memory_api.normalize_rules(None)
        save_global_rules(rules)
        return rules
    normalized = _memory_api.normalize_rules(rules)
    if normalized != rules:
        save_global_rules(normalized)
    elif db_rules == {}:
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_rules_payload(conn, "global", normalized)
        )
    return normalized


def save_global_rules(rules: dict):
    normalized = _memory_api.normalize_rules(rules)
    _memory_api._write_json_mirror(_memory_api.GLOBAL_RULES_PATH, normalized)
    _memory_api._sync_global_to_db_best_effort(
        lambda conn: _memory_api.sync_rules_payload(conn, "global", normalized)
    )


def load_project_rules(project_name: str) -> dict:
    db_rules = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_rules_payload(conn, "project"),
        "project rules",
    )
    if db_rules is not None:
        return _memory_api.normalize_rules(db_rules)
    path = _memory_api.project_path(project_name) / "rules.json"
    if not path.exists():
        rules = _memory_api.normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules

    try:
        rules = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except (_memory_api.json.JSONDecodeError, OSError):
        rules = _memory_api.normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules
    normalized = _memory_api.normalize_rules(rules)
    if normalized != rules:
        save_project_rules(project_name, normalized)
    elif db_rules == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_rules_payload(conn, "project", normalized),
        )
    return normalized


def save_project_rules(project_name: str, rules: dict):
    path = _memory_api.project_path(project_name) / "rules.json"
    normalized = _memory_api.normalize_rules(rules)
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_rules_payload(conn, "project", normalized),
    )


def _load_prompt_options_file(path: _memory_api.Path, scope: str) -> list[dict]:
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return _memory_api.normalize_prompt_options_payload(raw, scope=scope)


def _save_prompt_options_file(path: _memory_api.Path, options: list[dict], scope: str) -> list[dict]:
    normalized = _memory_api.normalize_prompt_options_payload(options, scope=scope)
    _memory_api._write_json_mirror(path, normalized)
    return normalized


def load_global_prompt_options() -> list[dict]:
    _memory_api.GLOBAL_PROMPT_OPTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    db_items = _memory_api._load_global_from_db_best_effort(
        lambda conn: _memory_api.load_prompt_options_payload(conn, "global"),
        "global prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="global")
    items = _load_prompt_options_file(_memory_api.GLOBAL_PROMPT_OPTIONS_PATH, "global")
    if db_items == [] and items:
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "global", items)
        )
    return items


def save_global_prompt_options(options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api.GLOBAL_PROMPT_OPTIONS_PATH, options, "global")
    _memory_api._sync_global_to_db_best_effort(
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "global", normalized)
    )
    return normalized


def load_project_prompt_options(project_name: str) -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_prompt_options_payload(conn, "project"),
        "project prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="project")
    items = _load_prompt_options_file(_memory_api._project_prompt_options_path(project_name), "project")
    if db_items == [] and items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "project", items),
        )
    return items


def save_project_prompt_options(project_name: str, options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api._project_prompt_options_path(project_name), options, "project")
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "project", normalized),
    )
    return normalized


def load_story_prompt_options(project_name: str, story_id: str = "default") -> list[dict]:
    db_items = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_prompt_options_payload(conn, "story", story_id),
        "story prompt options",
    )
    if db_items is not None:
        return _memory_api.normalize_prompt_options_payload(db_items, scope="story")
    items = _load_prompt_options_file(_memory_api._story_prompt_options_path(project_name, story_id), "story")
    if db_items == [] and items:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_prompt_options_payload(conn, "story", items, story_id),
        )
    return items


def save_story_prompt_options(project_name: str, story_id: str, options: list[dict]) -> list[dict]:
    normalized = _save_prompt_options_file(_memory_api._story_prompt_options_path(project_name, story_id), options, "story")
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_prompt_options_payload(conn, "story", normalized, story_id),
    )
    return normalized


def upsert_prompt_option(project_name: str, layer: str, option: dict, story_id: str = "default") -> dict:
    normalized_layer = str(layer or "story").strip().lower()
    if normalized_layer == "global":
        existing = load_global_prompt_options()
        scope = "global"
    elif normalized_layer == "project":
        existing = load_project_prompt_options(project_name)
        scope = "project"
    elif normalized_layer == "story":
        existing = load_story_prompt_options(project_name, story_id)
        scope = "story"
    else:
        raise ValueError(f"Unknown prompt option layer: {layer}")

    normalized_option = _memory_api.normalize_prompt_options_payload([option], scope=scope)[0]
    updated = []
    replaced = False
    for item in existing:
        if item.get("id") == normalized_option["id"]:
            updated.append(normalized_option)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(normalized_option)

    if normalized_layer == "global":
        save_global_prompt_options(updated)
    elif normalized_layer == "project":
        save_project_prompt_options(project_name, updated)
    else:
        save_story_prompt_options(project_name, story_id, updated)
    return normalized_option


def delete_prompt_option(project_name: str, layer: str, option_id: str, story_id: str = "default") -> bool:
    target_id = str(option_id or "").strip()
    normalized_layer = str(layer or "story").strip().lower()
    if normalized_layer == "global":
        existing = load_global_prompt_options()
        kept = [item for item in existing if item.get("id") != target_id]
        save_global_prompt_options(kept)
    elif normalized_layer == "project":
        existing = load_project_prompt_options(project_name)
        kept = [item for item in existing if item.get("id") != target_id]
        save_project_prompt_options(project_name, kept)
    elif normalized_layer == "story":
        existing = load_story_prompt_options(project_name, story_id)
        kept = [item for item in existing if item.get("id") != target_id]
        save_story_prompt_options(project_name, story_id, kept)
    else:
        raise ValueError(f"Unknown prompt option layer: {layer}")
    return len(kept) != len(existing)
