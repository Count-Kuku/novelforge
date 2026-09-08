"""SQLite repository for immutable reference releases and story copies.

The repository deliberately owns only SQL and row mapping.  It never reads the
current project knowledge while a binding is being copied: a ready release is
the immutable manifest used by the copy transaction.  This is what prevents a
source re-extraction from changing an existing story copy.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import uuid4

from storage.repositories.entity_identity import entity_id_for


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _object_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return list(parsed) if isinstance(parsed, list) else []


def _row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _rows(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]


def _stable_id(prefix: str, *parts: Any) -> str:
    digest = hashlib.sha256("|".join(str(item or "") for item in parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}_{digest}"


def create_reference_library(
    conn: sqlite3.Connection,
    *,
    project_name: str,
    title: str,
    source_kind: str = "reference",
    source_id: str | None = None,
    library_id: str | None = None,
) -> dict[str, Any]:
    """Create or return one project-owned library.

    ``library_id`` is accepted for deterministic import retries.  If it is
    already present, the existing row is returned without changing its title.
    """

    clean_project = str(project_name or "").strip()
    clean_title = str(title or "").strip()
    if not clean_project or not clean_title:
        raise ValueError("project_name 和资料标题不能为空。")
    clean_id = str(library_id or "").strip() or f"library_{uuid4().hex}"
    existing = conn.execute("SELECT * FROM reference_libraries WHERE library_id = ?", (clean_id,)).fetchone()
    if existing is not None:
        if str(existing["project_name"]) != clean_project:
            raise ValueError("资料库不属于当前项目。")
        return dict(existing)
    now = _now()
    conn.execute(
        """
        INSERT INTO reference_libraries
            (library_id, project_name, title, source_kind, source_id, status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (clean_id, clean_project, clean_title, str(source_kind or "reference"), str(source_id or "").strip() or None, now, now),
    )
    return dict(conn.execute("SELECT * FROM reference_libraries WHERE library_id = ?", (clean_id,)).fetchone())


def list_reference_libraries(
    conn: sqlite3.Connection, *, project_name: str, include_archived: bool = False
) -> list[dict[str, Any]]:
    where = "project_name = ?" if include_archived else "project_name = ? AND status = 'active'"
    return _rows(conn, f"SELECT * FROM reference_libraries WHERE {where} ORDER BY updated_at DESC, library_id", (project_name,))


def ensure_reference_libraries_for_project(conn: sqlite3.Connection, *, project_name: str) -> list[dict[str, Any]]:
    """Materialize ordinary confirmed project imports as user-visible libraries.

    The import workflow already owns extraction and confirmation.  This small
    reconciliation groups those rows by every reliable source/evidence source
    and freezes a release, so the UI's library view does not require a second
    manual "create library / publish release" ceremony.
    """

    project_rows = conn.execute(
        """
        SELECT knowledge_id, source_id
        FROM knowledge_items
        WHERE story_id IS NULL AND setting_scope = 'project'
          AND status = 'confirmed' AND deleted_at IS NULL
        ORDER BY knowledge_id
        """
    ).fetchall()
    groups: dict[str, set[str]] = {}
    for row in project_rows:
        knowledge_id = str(row["knowledge_id"] or "").strip()
        source_ids = {str(row["source_id"] or "").strip()} if str(row["source_id"] or "").strip() else set()
        source_ids.update(
            str(evidence[0] or "").strip()
            for evidence in conn.execute(
                "SELECT DISTINCT source_id FROM knowledge_evidence WHERE knowledge_id = ? AND source_id IS NOT NULL",
                (knowledge_id,),
            ).fetchall()
            if str(evidence[0] or "").strip()
        )
        for source_id in source_ids:
            groups.setdefault(source_id, set()).add(knowledge_id)
    for source_id, knowledge_ids in groups.items():
        source = conn.execute("SELECT title, source_type FROM source_documents WHERE source_id = ?", (source_id,)).fetchone()
        title = str(source[0] or "").strip() if source is not None else ""
        title = title or f"项目资料 · {source_id}"
        library = conn.execute(
            "SELECT * FROM reference_libraries WHERE project_name = ? AND source_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (project_name, source_id),
        ).fetchone()
        if library is None:
            archived = conn.execute(
                "SELECT 1 FROM reference_libraries WHERE project_name = ? AND source_id = ? AND status = 'archived' LIMIT 1",
                (project_name, source_id),
            ).fetchone()
            if archived is not None:
                # Archive is an explicit opt-out from automatic discovery.
                continue
        if library is None:
            library = create_reference_library(
                conn,
                project_name=project_name,
                title=title,
                source_kind=str(source[1] or "reference") if source is not None else "reference",
                source_id=source_id,
            )
            library_id = str(library["library_id"])
        else:
            library_id = str(library["library_id"])
        create_reference_library_release(conn, library_id=library_id, knowledge_ids=sorted(knowledge_ids))
    return list_reference_libraries(conn, project_name=project_name)


def load_reference_library(conn: sqlite3.Connection, library_id: str) -> dict[str, Any] | None:
    return _row_dict(conn.execute("SELECT * FROM reference_libraries WHERE library_id = ?", (str(library_id or "").strip(),)).fetchone())


def archive_reference_library(conn: sqlite3.Connection, library_id: str) -> bool:
    return bool(
        conn.execute(
            "UPDATE reference_libraries SET status = 'archived', archived_at = COALESCE(archived_at, ?), updated_at = ? WHERE library_id = ? AND status <> 'archived'",
            (_now(), _now(), str(library_id or "").strip()),
        ).rowcount
    )


def _knowledge_snapshot(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    knowledge_id = str(row["knowledge_id"])
    item = dict(row)
    item["content_json"] = _object(item.get("content_json"))
    item["structured_json"] = _object(item.get("structured_json"))
    # source_revision_id lives in the canonical extraction payload for older
    # knowledge rows; expose it in the release manifest so historical source
    # revisions are frozen by identity instead of silently falling back to the
    # current active revision.
    item["source_revision_id"] = str(
        item["content_json"].get("source_revision_id")
        or item["content_json"].get("source_revision")
        or ""
    ).strip() or None
    revision = conn.execute(
        "SELECT * FROM knowledge_revisions WHERE knowledge_id = ? ORDER BY revision_no DESC LIMIT 1",
        (knowledge_id,),
    ).fetchone()
    evidence = _rows(conn, "SELECT * FROM knowledge_evidence WHERE knowledge_id = ? ORDER BY evidence_id", (knowledge_id,))
    for entry in evidence:
        entry["location_json"] = _object(entry.get("location_json"))
    entity_id = str(row["entity_id"] or "").strip() if "entity_id" in row.keys() else ""
    entity = _row_dict(conn.execute("SELECT * FROM entities WHERE entity_id = ?", (entity_id,)).fetchone()) if entity_id else None
    alias_groups: list[dict[str, Any]] = []
    if entity is not None:
        alias_group_id = str(entity.get("alias_group_id") or "").strip()
        canonical_name = str(entity.get("canonical_name") or item.get("name") or "").strip()
        entity_type = str(entity.get("entity_type") or "").strip()
        worldline_id = str(entity.get("worldline_id") or item.get("worldline_id") or "").strip()
        alias_rows = conn.execute(
            """
            SELECT * FROM entity_alias_groups
            WHERE deleted_at IS NULL
              AND (
                (? <> '' AND alias_group_id = ?)
                OR (
                    canonical_name = ?
                    AND COALESCE(entity_type, '') = COALESCE(?, '')
                    AND COALESCE(worldline_id, '') = COALESCE(?, '')
                    AND story_id IS NULL
                )
                OR json_extract(metadata_json, '$.knowledge_id') = ?
                OR json_extract(metadata_json, '$.id') = ?
              )
            ORDER BY alias_group_id
            """,
            (alias_group_id, alias_group_id, canonical_name, entity_type, worldline_id, knowledge_id, knowledge_id),
        ).fetchall()
        for alias_row in alias_rows:
            alias = dict(alias_row)
            alias["aliases"] = _object_list(alias.get("aliases_json"))
            alias["metadata"] = _object(alias.get("metadata_json"))
            alias_groups.append(alias)
    # Some older imports kept aliases on the extraction payload without a
    # materialized alias-group row. Preserve that identity in the immutable
    # manifest so the story copy can materialize a local group instead of
    # silently reducing aliases to display JSON.
    payload_aliases = item.get("aliases")
    if isinstance(payload_aliases, list) and payload_aliases and not alias_groups:
        alias_groups.append({
            "alias_group_id": str(item.get("alias_group_id") or f"knowledge:{knowledge_id}"),
            "canonical_name": str(entity.get("canonical_name") if entity else item.get("name") or ""),
            "aliases": list(payload_aliases),
            "entity_type": str(entity.get("entity_type") if entity else item.get("category") or ""),
            "worldline_id": str(entity.get("worldline_id") if entity else item.get("worldline_id") or "") or None,
            "metadata": {"knowledge_id": knowledge_id},
        })
    edges = _rows(
        conn,
        "SELECT * FROM graph_edges WHERE deleted_at IS NULL AND json_extract(metadata_json, '$.knowledge_id') = ? ORDER BY edge_id",
        (knowledge_id,),
    )
    endpoint_ids = {str(edge.get(key) or "") for edge in edges for key in ("source_node_id", "target_node_id")} - {""}
    related_entities = []
    if endpoint_ids:
        marks = ",".join("?" for _ in endpoint_ids)
        related_entities = _rows(conn, f"SELECT * FROM entities WHERE entity_id IN ({marks}) ORDER BY entity_id", tuple(sorted(endpoint_ids)))
    alias_ids = {str(entry.get("alias_group_id") or "") for entry in related_entities} - {""}
    known_alias_ids = {str(entry.get("alias_group_id") or "") for entry in alias_groups}
    for alias_id in sorted(alias_ids - known_alias_ids):
        alias = _row_dict(conn.execute("SELECT * FROM entity_alias_groups WHERE alias_group_id=? AND deleted_at IS NULL", (alias_id,)).fetchone())
        if alias:
            alias["aliases"] = _object_list(alias.get("aliases_json"))
            alias["metadata"] = _object(alias.get("metadata_json"))
            alias_groups.append(alias)
    return {
        "knowledge": item,
        "revision": dict(revision) if revision is not None else None,
        "evidence": evidence,
        "entity": entity,
        "alias_groups": alias_groups,
        "edges": edges,
        "related_entities": related_entities,
    }


def create_reference_library_release(
    conn: sqlite3.Connection,
    *,
    library_id: str,
    knowledge_ids: Iterable[str] | None = None,
    release_id: str | None = None,
    content_hash: str | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze project-owned confirmed knowledge into an immutable release."""

    library = load_reference_library(conn, library_id)
    if library is None:
        raise ValueError("资料库不存在。")
    if library["status"] != "active":
        raise ValueError("归档资料库不能发布新版本。")
    ids = list(dict.fromkeys(str(item or "").strip() for item in (knowledge_ids or []) if str(item or "").strip()))
    if ids:
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"SELECT * FROM knowledge_items WHERE knowledge_id IN ({placeholders}) AND deleted_at IS NULL AND status = 'confirmed' AND story_id IS NULL AND setting_scope = 'project' ORDER BY knowledge_id",
            tuple(ids),
        ).fetchall()
        found_ids = {str(row["knowledge_id"]) for row in rows}
        missing_ids = [item for item in ids if item not in found_ids]
        if missing_ids:
            raise ValueError(f"指定知识不存在、未确认或不属于项目作用域：{', '.join(missing_ids)}")
    else:
        rows = conn.execute(
            "SELECT * FROM knowledge_items WHERE deleted_at IS NULL AND status = 'confirmed' AND story_id IS NULL AND setting_scope = 'project' ORDER BY category, knowledge_id"
        ).fetchall()
    snapshots = [_knowledge_snapshot(conn, row) for row in rows]
    canonical = _json(snapshots)
    computed_digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    supplied_digest = str(content_hash or "").strip()
    if supplied_digest and supplied_digest != computed_digest:
        raise ValueError("release content_hash 与当前冻结内容不一致。")
    digest = computed_digest
    duplicate = conn.execute(
        "SELECT * FROM reference_library_releases WHERE library_id = ? AND content_hash = ?",
        (library_id, digest),
    ).fetchone()
    if duplicate is not None:
        return dict(duplicate)
    release_no = int(conn.execute("SELECT COALESCE(MAX(release_no), 0) + 1 FROM reference_library_releases WHERE library_id = ?", (library_id,)).fetchone()[0])
    clean_release_id = str(release_id or "").strip() or f"release_{uuid4().hex}"
    now = _now()
    release_manifest = dict(manifest or {})
    release_manifest.setdefault("item_count", len(snapshots))
    release_manifest.setdefault("knowledge_ids", [str(row["knowledge"]["knowledge_id"]) for row in snapshots])
    conn.execute(
        """
        INSERT INTO reference_library_releases
            (release_id, library_id, release_no, content_hash, status, manifest_json, created_at, ready_at)
        VALUES (?, ?, ?, ?, 'ready', ?, ?, ?)
        """,
        (clean_release_id, library_id, release_no, digest, _json(release_manifest), now, now),
    )
    for ordinal, snapshot in enumerate(snapshots):
        knowledge = snapshot["knowledge"]
        revision = snapshot.get("revision") or {}
        entity = snapshot.get("entity") or {}
        conn.execute(
            """
            INSERT INTO reference_library_release_items
                (release_id, item_kind, origin_id, origin_revision_id, source_id, source_revision_id, payload_json, ordinal)
            VALUES (?, 'knowledge', ?, ?, ?, ?, ?, ?)
            """,
            (
                clean_release_id,
                knowledge["knowledge_id"],
                revision.get("revision_id"),
                knowledge.get("source_id"),
                revision.get("source_revision_id") or knowledge.get("source_revision_id"),
                _json({**snapshot, "origin_entity_id": entity.get("entity_id")}),
                ordinal,
            ),
        )
    _freeze_release_sources(conn, clean_release_id, snapshots)
    conn.execute("UPDATE reference_libraries SET updated_at = ? WHERE library_id = ?", (now, library_id))
    return dict(conn.execute("SELECT * FROM reference_library_releases WHERE release_id = ?", (clean_release_id,)).fetchone())


def list_reference_library_releases(conn: sqlite3.Connection, library_id: str) -> list[dict[str, Any]]:
    return _rows(conn, "SELECT * FROM reference_library_releases WHERE library_id = ? ORDER BY release_no DESC", (library_id,))


def load_reference_library_release(conn: sqlite3.Connection, release_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM reference_library_releases WHERE release_id = ?", (release_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["manifest_json"] = _object(result.get("manifest_json"))
    result["items"] = []
    for item in conn.execute("SELECT * FROM reference_library_release_items WHERE release_id = ? ORDER BY ordinal, origin_id", (release_id,)).fetchall():
        entry = dict(item)
        entry["payload_json"] = _object(entry.get("payload_json"))
        result["items"].append(entry)
    return result


def _freeze_release_sources(conn: sqlite3.Connection, release_id: str, snapshots: list[dict[str, Any]]) -> None:
    source_ids: set[str] = set()
    revisions_by_source: dict[str, set[str]] = {}
    for snapshot in snapshots:
        knowledge = snapshot.get("knowledge") or {}
        source_id = str(knowledge.get("source_id") or "").strip()
        if source_id:
            source_ids.add(source_id)
        revision = snapshot.get("revision") or {}
        revision_id = str(revision.get("source_revision_id") or "").strip()
        if source_id and revision_id:
            revisions_by_source.setdefault(source_id, set()).add(revision_id)
        for evidence in snapshot.get("evidence") or []:
            evidence_source = str(evidence.get("source_id") or "").strip()
            if evidence_source:
                source_ids.add(evidence_source)
                evidence_revision = str(evidence.get("source_revision_id") or "").strip()
                if evidence_revision:
                    revisions_by_source.setdefault(evidence_source, set()).add(evidence_revision)
    for source_id in sorted(source_ids):
        source_row = conn.execute("SELECT * FROM source_documents WHERE source_id = ?", (source_id,)).fetchone()
        if source_row is None:
            continue
        source_json = dict(source_row)
        revision_ids = set(revisions_by_source.get(source_id) or set())
        if not revision_ids:
            active_revision = str(source_json.get("active_revision_id") or "").strip()
            if active_revision:
                revision_ids.add(active_revision)
        if not revision_ids:
            latest = conn.execute(
                "SELECT revision_id FROM source_revisions WHERE source_id = ? ORDER BY created_at DESC, revision_id DESC LIMIT 1",
                (source_id,),
            ).fetchone()
            revision_ids.add(str(latest[0])) if latest is not None else revision_ids.add("")
        for revision_id in sorted(revision_ids):
            revision_row = conn.execute(
                "SELECT * FROM source_revisions WHERE revision_id = ?",
                (revision_id,),
            ).fetchone() if revision_id else None
            if revision_row is None and revision_id:
                # Evidence pointed at a revision that is no longer present;
                # keep an explicit unavailable record rather than pretending
                # the current source is that historical revision.
                revision_json: dict[str, Any] = {"revision_id": revision_id, "unavailable": True}
            else:
                revision_json = dict(revision_row) if revision_row is not None else {}
            segment_rows = _rows(
                conn,
                "SELECT * FROM source_segments WHERE source_id = ? AND deleted_at IS NULL AND (? = '' OR source_revision_id = ?) ORDER BY segment_index, segment_id",
                (source_id, revision_id, revision_id),
            )
            chunk_rows = _rows(
                conn,
                """
                SELECT chunk.*, document.document_id, document.title AS document_title,
                       document.source_revision_id AS document_source_revision_id
                FROM retrieval_chunks AS chunk
                JOIN retrieval_documents AS document ON document.document_id = chunk.document_id
                WHERE document.source_id = ? AND chunk.deleted_at IS NULL AND document.deleted_at IS NULL
                  AND (? = '' OR COALESCE(chunk.source_revision_id, document.source_revision_id, '') = ?)
                ORDER BY document.document_id, chunk.chunk_index, chunk.chunk_id
                """,
                (source_id, revision_id, revision_id),
            )
            metadata = _object(revision_json.get("metadata_json"))
            raw_text = metadata.get("raw_text") or metadata.get("text") or metadata.get("content")
            if not raw_text and source_json.get("original_asset_id"):
                asset_payload = conn.execute(
                    "SELECT payload_json FROM asset_payloads WHERE asset_id = ?",
                    (source_json.get("original_asset_id"),),
                ).fetchone()
                payload_object = _object(asset_payload[0]) if asset_payload is not None else {}
                raw_text = payload_object.get("raw_text") or payload_object.get("text") or payload_object.get("content")
            declared_body_hash = str(
                metadata.get("source_body_hash")
                or metadata.get("raw_text_hash")
                or metadata.get("content_hash")
                or ""
            )
            verified = bool(
                isinstance(raw_text, str)
                and raw_text
                and declared_body_hash
                and declared_body_hash == hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            )
            status = "complete" if verified else "partial" if segment_rows or chunk_rows else "unavailable"
            conn.execute(
                """
                INSERT INTO reference_library_release_sources
                    (release_id, source_id, revision_id, source_json, revision_json,
                     segments_json, chunks_json, snapshot_status, content_hash_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(release_id, source_id, revision_id) DO NOTHING
                """,
                (
                    release_id,
                    source_id,
                    revision_id,
                    _json(source_json),
                    _json({**revision_json, "raw_text": raw_text} if verified else revision_json),
                    _json(segment_rows),
                    _json(chunk_rows),
                    status,
                    1 if verified else 0,
                ),
            )


def load_reference_library_release_sources(
    conn: sqlite3.Connection,
    *,
    release_id: str,
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    params: list[Any] = [release_id]
    where = "release_id = ?"
    if source_id:
        where += " AND source_id = ?"
        params.append(source_id)
    result: list[dict[str, Any]] = []
    for row in conn.execute(f"SELECT * FROM reference_library_release_sources WHERE {where} ORDER BY source_id, revision_id", params).fetchall():
        entry = dict(row)
        entry["source_json"] = _object(entry.get("source_json"))
        entry["revision_json"] = _object(entry.get("revision_json"))
        try:
            entry["segments_json"] = json.loads(str(entry.get("segments_json") or "[]"))
        except (TypeError, ValueError):
            entry["segments_json"] = []
        try:
            entry["chunks_json"] = json.loads(str(entry.get("chunks_json") or "[]"))
        except (TypeError, ValueError):
            entry["chunks_json"] = []
        result.append(entry)
    return result


def ensure_story_reference_state(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    default_mode: str = "legacy",
) -> dict[str, Any]:
    mode = "strict" if str(default_mode).strip().lower() == "strict" else "legacy"
    row = conn.execute("SELECT * FROM story_reference_states WHERE story_id = ?", (story_id,)).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO story_reference_states (story_id, read_mode, migration_status) VALUES (?, ?, ?)",
            (story_id, mode, "not_required" if mode == "strict" else "pending"),
        )
        row = conn.execute("SELECT * FROM story_reference_states WHERE story_id = ?", (story_id,)).fetchone()
    return dict(row)


def mark_story_reference_strict(conn: sqlite3.Connection, *, story_id: str, binding_id: str | None = None) -> dict[str, Any]:
    ensure_story_reference_state(conn, story_id=story_id)
    conn.execute(
        """
        UPDATE story_reference_states
        SET read_mode = 'strict', migration_status = 'confirmed', confirmed_at = COALESCE(confirmed_at, ?),
            migrated_binding_id = COALESCE(?, migrated_binding_id), updated_at = ?
        WHERE story_id = ?
        """,
        (_now(), binding_id, _now(), story_id),
    )
    return dict(conn.execute("SELECT * FROM story_reference_states WHERE story_id = ?", (story_id,)).fetchone())


def load_story_reference_state(conn: sqlite3.Connection, *, story_id: str) -> dict[str, Any]:
    return ensure_story_reference_state(conn, story_id=story_id)


def _active_binding(conn: sqlite3.Connection, story_id: str, library_id: str, branch_id: str | None) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM story_library_bindings
        WHERE story_id = ? AND library_id = ? AND COALESCE(branch_id, '') = COALESCE(?, '')
          AND status <> 'archived'
        ORDER BY updated_at DESC LIMIT 1
        """,
        (story_id, library_id, branch_id),
    ).fetchone()


def _copy_release_item(conn: sqlite3.Connection, binding: sqlite3.Row, entry: sqlite3.Row) -> dict[str, Any]:
    from storage.repositories.knowledge import upsert_knowledge_category_item

    payload = _object(entry["payload_json"])
    source = _object(payload.get("knowledge"))
    origin_id = str(entry["origin_id"] or source.get("knowledge_id") or "").strip()
    local_id = _stable_id("story_knowledge", binding["binding_id"], origin_id)
    historical = conn.execute(
        """
        SELECT link.local_knowledge_id, link.state
        FROM story_library_item_links AS link
        JOIN story_library_bindings AS previous ON previous.binding_id = link.binding_id
        WHERE previous.story_id = ? AND COALESCE(previous.branch_id, '') = COALESCE(?, '') AND link.origin_knowledge_id = ?
        ORDER BY link.updated_at DESC LIMIT 1
        """,
        (binding["story_id"], binding["branch_id"], origin_id),
    ).fetchone()
    if historical is not None and str(historical["state"] or "") in {"tombstone", "deleted"}:
        # A previous explicit delete is sticky across a retry/rebind.  Keep a
        # traceable link in the new binding without materializing the item.
        baseline = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
        conn.execute(
            """
            INSERT INTO story_library_item_links
                (binding_id, origin_knowledge_id, origin_revision_id, origin_entity_id,
                 local_knowledge_id, local_entity_id, baseline_hash, state)
            VALUES (?, ?, ?, ?, ?, NULL, ?, 'tombstone')
            """,
            (binding["binding_id"], origin_id, entry["origin_revision_id"], payload.get("origin_entity_id") or _object(payload.get("entity")).get("entity_id"), historical["local_knowledge_id"], baseline),
        )
        return dict(conn.execute("SELECT * FROM story_library_item_links WHERE binding_id = ? AND origin_knowledge_id = ?", (binding["binding_id"], origin_id)).fetchone())
    existing_link = conn.execute(
        "SELECT * FROM story_library_item_links WHERE binding_id = ? AND origin_knowledge_id = ?",
        (binding["binding_id"], origin_id),
    ).fetchone()
    if existing_link is not None:
        return dict(existing_link)
    existing_local = conn.execute("SELECT * FROM knowledge_items WHERE knowledge_id = ?", (local_id,)).fetchone()
    if existing_local is None:
        # content_json is the canonical extraction payload. Start from it so
        # aliases, version_scope, source anchors and temporal fields survive.
        content = _object(source.get("content_json"))
        if not content:
            content = dict(source)
        source_alias_groups = [
            dict(group)
            for group in (payload.get("alias_groups") or [])
            if isinstance(group, dict)
        ]
        if not source_alias_groups and isinstance(content.get("aliases"), list) and content.get("aliases"):
            source_alias_groups = [{
                "alias_group_id": str(content.get("alias_group_id") or f"knowledge:{origin_id}"),
                "canonical_name": str(source.get("name") or content.get("name") or ""),
                "aliases": list(content.get("aliases") or []),
                "entity_type": str(source.get("category") or ""),
                "worldline_id": str(source.get("worldline_id") or content.get("worldline_id") or "") or None,
                "metadata": {"knowledge_id": origin_id},
            }]
        local_alias_ids: dict[str, str] = {}
        for source_alias in source_alias_groups:
            source_alias_id = str(source_alias.get("alias_group_id") or "").strip() or f"knowledge:{origin_id}"
            local_alias_id = _stable_id("story_alias", binding["binding_id"], origin_id, source_alias_id)
            aliases = source_alias.get("aliases")
            if not isinstance(aliases, list):
                aliases = _object_list(source_alias.get("aliases_json"))
            alias_metadata = _object(source_alias.get("metadata") or source_alias.get("metadata_json"))
            alias_metadata["_story_library"] = {
                "binding_id": binding["binding_id"],
                "origin_knowledge_id": origin_id,
                "origin_alias_group_id": source_alias_id,
            }
            conn.execute(
                """
                INSERT INTO entity_alias_groups
                    (alias_group_id, canonical_name, aliases_json, entity_type, story_id,
                     worldline_id, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(alias_group_id) DO NOTHING
                """,
                (
                    local_alias_id,
                    str(source_alias.get("canonical_name") or source.get("name") or content.get("name") or ""),
                    _json(aliases),
                    str(source_alias.get("entity_type") or source.get("category") or "").strip() or None,
                    binding["story_id"],
                    str(source_alias.get("worldline_id") or source.get("worldline_id") or content.get("worldline_id") or "").strip() or None,
                    _json(alias_metadata),
                ),
            )
            local_alias_ids[source_alias_id] = local_alias_id
        content["_story_library"] = {
            "binding_id": binding["binding_id"],
            "library_id": binding["library_id"],
            "release_id": binding["release_id"],
            "origin_knowledge_id": origin_id,
            "origin_revision_id": entry["origin_revision_id"],
            "source_revision_id": entry["source_revision_id"],
            "branch_id": binding["branch_id"],
        }
        normalized = {
            **content,
            "id": local_id,
            "knowledge_id": local_id,
            "category": source.get("category") or content.get("category") or "",
            "name": source.get("name") or content.get("name") or "",
            "title": source.get("title") or content.get("title") or "",
            "summary": source.get("summary") or content.get("summary") or "",
            "content_json": content,
            "typed_data": _object(source.get("structured_json")) or _object(content.get("typed_data")),
            "story_id": binding["story_id"],
            "branch_id": binding["branch_id"],
            "setting_scope": "story",
            "setting_role": source.get("setting_role"),
            "injection_policy": source.get("injection_policy"),
            "canon_status": source.get("canon_status"),
            "worldline_id": source.get("worldline_id") or content.get("worldline_id"),
            "version_scope": content.get("version_scope") or _object(payload.get("entity")).get("version_scope") or "project_main",
            "worldline_name": source.get("worldline_name") or content.get("worldline_name"),
            "confidence": source.get("confidence"),
            "importance": source.get("importance"),
            "evidence_strength": source.get("evidence_strength"),
            "source_id": source.get("source_id"),
            "segment_id": source.get("segment_id"),
            "source_revision_id": entry["source_revision_id"],
            "extraction_mode": source.get("extraction_mode"),
            "status": source.get("status") or "confirmed",
            "schema_version": source.get("schema_version") or 1,
            "fact_key": source.get("fact_key") or content.get("fact_key"),
            "chapter_no": source.get("chapter_no") or content.get("chapter_no"),
            "evidence": payload.get("evidence") or [],
        }
        upsert_knowledge_category_item(conn, str(normalized["category"]), normalized)
        # 021 owns the physical column; writing it immediately after the
        # upsert keeps the canonical JSON and SQL projection in sync.
        conn.execute(
            """
            UPDATE knowledge_items
            SET branch_id = ?, valid_from_chapter = ?, valid_to_chapter = ?,
                superseded_by = ?, chapter_no = ?, merge_policy = COALESCE(?, merge_policy)
            WHERE knowledge_id = ?
            """,
            (
                binding["branch_id"],
                source.get("valid_from_chapter"),
                source.get("valid_to_chapter"),
                _stable_id("story_knowledge", binding["binding_id"], str(source["superseded_by"])) if source.get("superseded_by") else None,
                source.get("chapter_no"),
                source.get("merge_policy"),
                local_id,
            ),
        )
        source_edges = payload.get("edges") if isinstance(payload.get("edges"), list) else []
        entity_map: dict[str, str] = {}
        origin_entity_ids = set()
        origin_entity = _object(payload.get("entity"))
        frozen_entities = {
            str(entity.get("entity_id") or ""): dict(entity)
            for entity in payload.get("related_entities", []) if isinstance(entity, dict)
        }
        if origin_entity.get("entity_id"):
            origin_entity_ids.add(str(origin_entity["entity_id"]))
            frozen_entities[str(origin_entity["entity_id"])] = origin_entity
        for source_edge in source_edges:
            if isinstance(source_edge, dict):
                for key in ("source_node_id", "target_node_id"):
                    if source_edge.get(key):
                        origin_entity_ids.add(str(source_edge[key]))
        for origin_entity_id in sorted(origin_entity_ids):
            origin_row = frozen_entities.get(origin_entity_id)
            if origin_row is None:
                continue
            domain = (
                "story",
                str(binding["story_id"]),
                str(binding["branch_id"] or ""),
                str(origin_row["worldline_id"] or ""),
                str(origin_row["version_scope"] or "project_main"),
            )
            local_entity_id = entity_id_for(str(origin_row["entity_type"]), str(origin_row["canonical_name"]), domain)
            existing_identity = conn.execute(
                "SELECT entity_id FROM entities WHERE entity_type=? AND canonical_name=? AND story_id=? AND branch_id=? AND COALESCE(worldline_id,'')=? AND setting_scope='story' AND COALESCE(version_scope,'project_main')=? LIMIT 1",
                (origin_row["entity_type"], origin_row["canonical_name"], binding["story_id"], binding["branch_id"], origin_row["worldline_id"] or "", origin_row["version_scope"] or "project_main"),
            ).fetchone()
            if existing_identity:
                local_entity_id = str(existing_identity[0])
            local_row = conn.execute("SELECT entity_id FROM entities WHERE entity_id = ?", (local_entity_id,)).fetchone()
            if local_row is None:
                conn.execute(
                    """
                    INSERT INTO entities
                        (entity_id, entity_type, canonical_name, display_name, story_id, branch_id, worldline_id,
                         setting_scope, version_scope, summary, importance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'story', ?, ?, ?)
                    ON CONFLICT(entity_id) DO NOTHING
                    """,
                    (
                        local_entity_id,
                        origin_row["entity_type"],
                        origin_row["canonical_name"],
                        origin_row["display_name"],
                        binding["story_id"],
                        binding["branch_id"],
                        origin_row["worldline_id"],
                        origin_row["version_scope"] or "project_main",
                        origin_row["summary"] or "",
                        origin_row["importance"] or 0,
                    ),
                )
            entity_map[origin_entity_id] = local_entity_id
            conn.execute(
                """
                INSERT INTO story_library_entity_links
                    (binding_id, origin_entity_id, local_entity_id, entity_type, canonical_name, worldline_id)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(binding_id, origin_entity_id) DO NOTHING
                """,
                (binding["binding_id"], origin_entity_id, local_entity_id, origin_row["entity_type"], origin_row["canonical_name"], origin_row["worldline_id"]),
            )
            source_alias_id = str(origin_row["alias_group_id"] or "").strip()
            if not source_alias_id:
                source_alias_id = next(
                    (
                        str(group.get("alias_group_id") or "").strip()
                        for group in source_alias_groups
                        if str(group.get("canonical_name") or "").strip() == str(origin_row["canonical_name"] or "").strip()
                        and str(group.get("worldline_id") or "") == str(origin_row["worldline_id"] or "")
                    ),
                    "",
                )
            local_alias_id = local_alias_ids.get(source_alias_id)
            if local_alias_id:
                conn.execute(
                    "UPDATE entities SET alias_group_id = ?, updated_at = ? WHERE entity_id = ?",
                    (local_alias_id, _now(), local_entity_id),
                )
        local_edge_rows = [dict(row) for row in conn.execute(
            "SELECT * FROM graph_edges WHERE deleted_at IS NULL AND json_extract(metadata_json, '$.knowledge_id') = ? ORDER BY edge_id",
            (local_id,),
        ).fetchall()]
        for source_edge in source_edges:
            if not isinstance(source_edge, dict):
                continue
            source_entity_id = entity_map.get(str(source_edge.get("source_node_id") or ""))
            target_entity_id = entity_map.get(str(source_edge.get("target_node_id") or ""))
            if not source_entity_id or not target_entity_id:
                continue
            matching = next(
                (
                    row for row in local_edge_rows
                    if row.get("source_node_id") == source_entity_id
                    and row.get("target_node_id") == target_entity_id
                    and row.get("relation_type") == source_edge.get("relation_type")
                    and row.get("direction") == source_edge.get("direction")
                ),
                None,
            )
            if matching is None:
                continue
            conn.execute(
                """
                UPDATE graph_edges
                SET valid_from_chapter = ?, valid_to_chapter = ?,
                    chapter_no = ?, merge_policy = COALESCE(?, merge_policy)
                WHERE edge_id = ?
                """,
                (
                    source_edge.get("valid_from_chapter"),
                    source_edge.get("valid_to_chapter"),
                    source_edge.get("chapter_no"),
                    source_edge.get("merge_policy"),
                    matching["edge_id"],
                ),
            )
        existing_local = conn.execute("SELECT * FROM knowledge_items WHERE knowledge_id = ?", (local_id,)).fetchone()
    local_entity_id = str(existing_local["entity_id"] or "").strip() if existing_local is not None and "entity_id" in existing_local.keys() else ""
    origin_entity_id = str(payload.get("origin_entity_id") or _object(payload.get("entity")).get("entity_id") or "").strip() or None
    baseline = hashlib.sha256(_json(payload).encode("utf-8")).hexdigest()
    conn.execute(
        """
        INSERT INTO story_library_item_links
            (binding_id, origin_knowledge_id, origin_revision_id, origin_entity_id,
             local_knowledge_id, local_entity_id, baseline_hash, state)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
        """,
        (binding["binding_id"], origin_id, entry["origin_revision_id"], origin_entity_id, local_id, local_entity_id or None, baseline),
    )
    return dict(conn.execute("SELECT * FROM story_library_item_links WHERE binding_id = ? AND origin_knowledge_id = ?", (binding["binding_id"], origin_id)).fetchone())


def bind_story_library(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    library_id: str,
    release_id: str,
    branch_id: str | None = None,
    idempotency_key: str = "",
    legacy_migration: bool = False,
) -> dict[str, Any]:
    """Atomically materialize one immutable release into a story."""

    story = conn.execute("SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL", (story_id,)).fetchone()
    if story is None:
        raise ValueError("故事不存在。")
    release = load_reference_library_release(conn, release_id)
    if release is None or release["status"] != "ready" or release["library_id"] != library_id:
        raise ValueError("资料版本不存在、未就绪或不属于该资料库。")
    library = load_reference_library(conn, library_id)
    if library is None or library["status"] != "active":
        raise ValueError("资料库不存在或已归档。")
    existing = _active_binding(conn, story_id, library_id, branch_id)
    if existing is not None:
        if str(existing["release_id"]) != str(release_id):
            raise ValueError("该故事已绑定此资料库的其他版本，请使用显式更新操作。")
        return load_story_library_binding(conn, str(existing["binding_id"])) or dict(existing)
    binding_id = _stable_id("binding", story_id, branch_id or "", library_id, release_id)
    # An archived binding is historical.  Rebinding the same release gets a
    # fresh binding row while retaining deterministic local IDs, so an old
    # deleted copy cannot be silently resurrected by a uniqueness collision.
    if conn.execute("SELECT 1 FROM story_library_bindings WHERE binding_id = ?", (binding_id,)).fetchone() is not None:
        binding_id = f"{binding_id}_{uuid4().hex[:12]}"
    now = _now()
    conn.execute(
        """
        INSERT INTO story_library_bindings
            (binding_id, story_id, branch_id, library_id, release_id, status, idempotency_key, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'preparing', ?, ?, ?)
        """,
        (binding_id, story_id, branch_id, library_id, release_id, str(idempotency_key or ""), now, now),
    )
    binding = conn.execute("SELECT * FROM story_library_bindings WHERE binding_id = ?", (binding_id,)).fetchone()
    if binding is None:
        raise RuntimeError("资料绑定创建失败。")
    for entry in conn.execute("SELECT * FROM reference_library_release_items WHERE release_id = ? ORDER BY ordinal, origin_id", (release_id,)).fetchall():
        _copy_release_item(conn, binding, entry)
    conn.execute("UPDATE story_library_bindings SET status = 'ready', updated_at = ? WHERE binding_id = ?", (_now(), binding_id))
    result = load_story_library_binding(conn, binding_id)
    if result is None:
        raise RuntimeError("资料绑定提交失败。")
    mark_story_reference_strict(conn, story_id=story_id, binding_id=binding_id)
    result["legacy_migration"] = bool(legacy_migration)
    return result


def load_story_library_binding(conn: sqlite3.Connection, binding_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM story_library_bindings WHERE binding_id = ?", (binding_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["items"] = _rows(
        conn,
        "SELECT * FROM story_library_item_links WHERE binding_id = ? ORDER BY origin_knowledge_id",
        (binding_id,),
    )
    return result


def list_story_library_bindings(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    branch_id: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    where = ["story_id = ?"]
    params: list[Any] = [story_id]
    if branch_id is not None:
        where.append("(branch_id = ? OR branch_id IS NULL)")
        params.append(branch_id)
    if not include_archived:
        where.append("status = 'ready'")
    results = _rows(conn, f"SELECT * FROM story_library_bindings WHERE {' AND '.join(where)} ORDER BY updated_at DESC, binding_id", params)
    for result in results:
        result["items"] = _rows(conn, "SELECT * FROM story_library_item_links WHERE binding_id = ? ORDER BY origin_knowledge_id", (result["binding_id"],))
    return results


def unbind_story_library(
    conn: sqlite3.Connection,
    binding_id: str,
    *,
    expected_story_id: str | None = None,
    expected_branch_id: str | None = None,
) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM story_library_bindings WHERE binding_id = ?", (binding_id,)).fetchone()
    if row is None:
        return None
    if expected_story_id is not None and str(row["story_id"]) != str(expected_story_id):
        raise ValueError("资料绑定不属于当前故事。")
    if expected_branch_id is not None and str(row["branch_id"] or "") != str(expected_branch_id):
        raise ValueError("资料绑定不属于当前分支。")
    conn.execute(
        "UPDATE story_library_bindings SET status = 'archived', removed_at = COALESCE(removed_at, ?), updated_at = ? WHERE binding_id = ?",
        (_now(), _now(), binding_id),
    )
    return load_story_library_binding(conn, binding_id)


def resolve_story_reference_context(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    branch_id: str | None = None,
) -> dict[str, Any]:
    """Return the exact knowledge set visible to story generation.

    Project knowledge is intentionally absent unless it has a ready story
    binding.  Raw source text is represented only by evidence/source IDs.
    """

    bindings = list_story_library_bindings(conn, story_id=story_id, branch_id=branch_id)
    binding_ids = [str(item["binding_id"]) for item in bindings]
    links: list[dict[str, Any]] = []
    if binding_ids:
        placeholders = ",".join("?" for _ in binding_ids)
        links = _rows(conn, f"SELECT * FROM story_library_item_links WHERE binding_id IN ({placeholders}) AND state <> 'tombstone'", binding_ids)
    local_ids = [str(item["local_knowledge_id"]) for item in links if item.get("local_knowledge_id")]
    own_params: list[Any] = [story_id]
    branch_clause = ""
    if branch_id is not None:
        branch_clause = " AND (branch_id IS NULL OR branch_id = ?)"
        own_params.append(branch_id)
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
            (story_id,),
        ).fetchall()
    }
    own = _rows(
        conn,
        f"SELECT * FROM knowledge_items WHERE story_id = ? AND setting_scope = 'story' AND status = 'confirmed' AND deleted_at IS NULL{branch_clause} ORDER BY category, knowledge_id",
        own_params,
    )
    own = [item for item in own if str(item.get("knowledge_id") or "") not in disabled_ids]
    own_by_id = {str(item["knowledge_id"]): item for item in own}
    visible_ids = set(own_by_id)
    for local_id in local_ids:
        row = conn.execute("SELECT * FROM knowledge_items WHERE knowledge_id = ? AND status = 'confirmed' AND deleted_at IS NULL", (local_id,)).fetchone()
        if row is not None:
            if branch_id is None or row["branch_id"] is None or str(row["branch_id"]) == str(branch_id):
                own_by_id.setdefault(str(local_id), dict(row))
                visible_ids.add(str(local_id))
    return {
        "story_id": story_id,
        "branch_id": branch_id,
        "bindings": bindings,
        "links": links,
        "knowledge": list(own_by_id.values()),
        "visible_knowledge_ids": sorted(visible_ids),
        "source_ids": sorted({str(item.get("source_id")) for item in own_by_id.values() if item.get("source_id")}),
        "raw_sources_allowed": False,
    }


def list_visible_knowledge_ids(conn: sqlite3.Connection, *, story_id: str, branch_id: str | None = None) -> list[str]:
    return list(resolve_story_reference_context(conn, story_id=story_id, branch_id=branch_id)["visible_knowledge_ids"])


def migrate_legacy_story_library(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    library_id: str,
    release_id: str,
    branch_id: str | None = None,
) -> dict[str, Any]:
    """Explicit one-shot legacy migration; never runs during normal reads."""

    return bind_story_library(
        conn,
        story_id=story_id,
        library_id=library_id,
        release_id=release_id,
        branch_id=branch_id,
        idempotency_key=f"legacy:{story_id}:{library_id}:{release_id}",
        legacy_migration=True,
    )
