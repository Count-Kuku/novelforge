"""SQL repository for story branches and immutable branch checkpoints."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def default_branch_id(story_id: str) -> str:
    """Return the stable legacy main branch ID for a story."""
    # story_id is already a stable opaque identifier. Preserve it byte-for-byte
    # so distinct IDs such as ``a-b``/``ab`` and ``A``/``a`` cannot collide.
    return f"branch_main_{_clean(story_id) or 'story'}"


def _row(row: sqlite3.Row | dict | None) -> dict | None:
    return dict(row) if row is not None else None


def ensure_default_branch(conn: sqlite3.Connection, story_id: str, *, source_worldline_id: str = "main") -> dict:
    story_id = _clean(story_id)
    if not story_id:
        raise ValueError("Story ID is required.")
    story = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL", (story_id,)
    ).fetchone()
    if story is None:
        raise ValueError("Story does not exist or is archived.")
    branch_id = default_branch_id(story_id)
    now = _now()
    conn.execute(
        """
        INSERT INTO story_branches (
            branch_id, story_id, name, description, source_worldline_id,
            created_at, updated_at
        ) VALUES (?, ?, '主线', '默认主线', ?, ?, ?)
        ON CONFLICT(branch_id) DO UPDATE SET
            updated_at = excluded.updated_at,
            source_worldline_id = CASE
                WHEN story_branches.source_worldline_id = '' THEN excluded.source_worldline_id
                ELSE story_branches.source_worldline_id
            END
        """,
        (branch_id, story_id, _clean(source_worldline_id) or "main", now, now),
    )
    return load_branch_row(conn, branch_id) or {}


def load_branch_row(conn: sqlite3.Connection, branch_id: str) -> dict | None:
    row = conn.execute(
        """
        SELECT branch_id, story_id, name, description, parent_branch_id,
               fork_fragment_id, fork_checkpoint_id, head_checkpoint_id,
               revision, status, source_worldline_id, created_at, updated_at,
               archived_at
        FROM story_branches WHERE branch_id = ?
        """,
        (_clean(branch_id),),
    ).fetchone()
    return _row(row)


def load_branch_for_story(conn: sqlite3.Connection, story_id: str, branch_id: str) -> dict:
    branch = load_branch_row(conn, branch_id)
    if branch is None or branch["story_id"] != _clean(story_id):
        raise ValueError("Branch does not belong to the story.")
    return branch


def list_branch_rows(conn: sqlite3.Connection, story_id: str, *, include_archived: bool = False) -> list[dict]:
    query = """
        SELECT branch_id, story_id, name, description, parent_branch_id,
               fork_fragment_id, fork_checkpoint_id, head_checkpoint_id,
               revision, status, source_worldline_id, created_at, updated_at,
               archived_at
        FROM story_branches WHERE story_id = ?
    """
    params: list[Any] = [_clean(story_id)]
    if not include_archived:
        query += " AND status <> 'archived'"
    query += " ORDER BY CASE WHEN parent_branch_id IS NULL THEN 0 ELSE 1 END, created_at, branch_id"
    return [dict(row) for row in conn.execute(query, tuple(params)).fetchall()]


def create_branch_row(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    name: str,
    description: str = "",
    parent_branch_id: str | None = None,
    fork_fragment_id: str | None = None,
    fork_checkpoint_id: str | None = None,
    source_worldline_id: str = "main",
    branch_id: str | None = None,
) -> dict:
    story_id = _clean(story_id)
    name = _clean(name)
    if not story_id or not name:
        raise ValueError("Story ID and branch name are required.")
    story = conn.execute(
        "SELECT story_id FROM stories WHERE story_id = ? AND deleted_at IS NULL", (story_id,)
    ).fetchone()
    if story is None:
        raise ValueError("Story does not exist or is archived.")
    if parent_branch_id:
        parent = load_branch_for_story(conn, story_id, parent_branch_id)
        if parent["status"] == "archived":
            raise ValueError("Cannot fork from an archived branch.")
    branch_id = _clean(branch_id) or f"branch_{uuid4().hex}"
    now = _now()
    try:
        conn.execute(
            """
            INSERT INTO story_branches (
                branch_id, story_id, name, description, parent_branch_id,
                fork_fragment_id, fork_checkpoint_id, source_worldline_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                branch_id, story_id, name, _clean(description), _clean(parent_branch_id) or None,
                _clean(fork_fragment_id) or None, _clean(fork_checkpoint_id) or None,
                _clean(source_worldline_id) or "main", now, now,
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise ValueError("同一故事下已有同名活动世界线。") from exc
    return load_branch_row(conn, branch_id) or {}


def archive_branch_row(conn: sqlite3.Connection, story_id: str, branch_id: str) -> dict:
    branch = load_branch_for_story(conn, story_id, branch_id)
    if branch_id == default_branch_id(story_id):
        raise ValueError("默认主线不能归档。")
    child = conn.execute(
        "SELECT 1 FROM story_branches WHERE parent_branch_id = ? AND status <> 'archived' LIMIT 1",
        (branch_id,),
    ).fetchone()
    if child is not None:
        raise ValueError("仍有活动子线，不能归档该世界线。")
    now = _now()
    conn.execute(
        "UPDATE story_branches SET status = 'archived', archived_at = ?, updated_at = ? WHERE branch_id = ?",
        (now, now, branch_id),
    )
    return load_branch_row(conn, branch_id) or {}


def update_branch_row(conn: sqlite3.Connection, story_id: str, branch_id: str, updates: dict) -> dict:
    branch = load_branch_for_story(conn, story_id, branch_id)
    assignments: list[str] = []
    values: list[Any] = []
    if "name" in updates and _clean(updates.get("name")):
        assignments.append("name = ?")
        values.append(_clean(updates["name"]))
    if "description" in updates:
        assignments.append("description = ?")
        values.append(_clean(updates.get("description")))
    if "status" in updates:
        target = _clean(updates.get("status"))
        if target == "archived":
            return archive_branch_row(conn, story_id, branch_id)
        if target == "active":
            assignments.append("status = ?, archived_at = NULL")
            values.append(target)
    if assignments:
        assignments.append("updated_at = ?")
        values.extend([_now(), branch_id])
        try:
            conn.execute(
                f"UPDATE story_branches SET {', '.join(assignments)} WHERE branch_id = ?",
                tuple(values),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError("同一故事下已有同名活动世界线。") from exc
    return load_branch_row(conn, branch_id) or branch


def list_checkpoint_rows(conn: sqlite3.Connection, branch_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT checkpoint_id, branch_id, parent_checkpoint_id, revision,
               frontier_fragment_id, frontier_content_hash, baseline_revision,
               snapshot_manifest_json, snapshot_hash, extraction_status, reason, created_at
        FROM branch_checkpoints WHERE branch_id = ? ORDER BY revision, checkpoint_id
        """,
        (_clean(branch_id),),
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["snapshot_manifest"] = json.loads(item.pop("snapshot_manifest_json") or "{}")
        except (TypeError, ValueError):
            item["snapshot_manifest"] = {}
        result.append(item)
    return result


def load_checkpoint_row(conn: sqlite3.Connection, checkpoint_id: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM branch_checkpoints WHERE checkpoint_id = ?", (_clean(checkpoint_id),)
    ).fetchone()
    if row is None:
        return None
    item = dict(row)
    try:
        item["snapshot_manifest"] = json.loads(item.pop("snapshot_manifest_json") or "{}")
    except (TypeError, ValueError):
        item["snapshot_manifest"] = {}
    return item


def _knowledge_snapshot_rows(
    conn: sqlite3.Connection,
    story_id: str,
    branch_id: str,
    *,
    include_deleted: bool = False,
) -> list[dict]:
    deleted_clause = "" if include_deleted else " AND deleted_at IS NULL"
    rows = conn.execute(
        f"""
        SELECT * FROM knowledge_items
        WHERE 1 = 1{deleted_clause}
          AND status IN ('confirmed', 'deleted', 'tombstone')
          AND ((story_id = ? AND branch_id = ?) OR (story_id = ? AND setting_scope = 'story' AND branch_id IS NULL))
        ORDER BY COALESCE(sequence_order, 0), created_at, knowledge_id
        """,
        (story_id, branch_id, story_id),
    ).fetchall()
    return _enrich_knowledge_snapshot_rows(conn, [dict(row) for row in rows])


def _knowledge_origin_id(item: dict) -> str:
    """Return the inherited ID a branch-local knowledge row overrides, if any."""
    direct = _clean(item.get("origin_knowledge_id"))
    if direct:
        return direct
    payload = item.get("content_json")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            payload = {}
    if isinstance(payload, dict):
        return _clean(payload.get("origin_knowledge_id"))
    return ""


def _enrich_knowledge_snapshot_rows(
    conn: sqlite3.Connection,
    rows: list[dict],
) -> list[dict]:
    """把检查点需要的实体、证据和关系投影到不可变 knowledge payload。

    分支检查点不能只保存 ``knowledge_items`` 当前行：父线实体可能随后被编辑，
    而实体名、别名、关系和证据又是资料库/实体规划读取所需的引用。这里一次性
    物化与该批知识行相关的投影，后续上下文和分支资料库只读取检查点 payload。
    关系按本批知识归属选取，并一起冻结端点；端点不必有独立的角色事实。
    """
    if not rows:
        return []
    result = [dict(row) for row in rows]
    knowledge_ids = [
        _clean(row.get("knowledge_id") or row.get("id"))
        for row in result
        if _clean(row.get("knowledge_id") or row.get("id"))
    ]
    entity_ids = {
        _clean(row.get("entity_id"))
        for row in result
        if _clean(row.get("entity_id"))
    }
    edge_rows = []
    if knowledge_ids:
        placeholders = ",".join("?" for _ in knowledge_ids)
        edge_rows = conn.execute(
            f"""
            SELECT edge_id, story_id, source_node_id, target_node_id, relation_type,
                   direction, confidence, evidence_id, metadata_json,
                   valid_from_chapter, valid_to_chapter, merge_policy, chapter_no
            FROM graph_edges
            WHERE deleted_at IS NULL
              AND json_extract(metadata_json, '$.knowledge_id') IN ({placeholders})
            ORDER BY updated_at, edge_id
            """,
            tuple(knowledge_ids),
        ).fetchall()
        for edge in edge_rows:
            entity_ids.update(value for value in (
                _clean(edge["source_node_id"]), _clean(edge["target_node_id"])
            ) if value)
    entities: dict[str, dict] = {}
    if entity_ids:
        placeholders = ",".join("?" for _ in entity_ids)
        entity_rows = conn.execute(
            f"""
            SELECT entity_id, entity_type, canonical_name, display_name, story_id,
                   branch_id, worldline_id, setting_scope, version_scope, summary,
                   alias_group_id, meta_json
            FROM entities WHERE entity_id IN ({placeholders})
            """,
            tuple(sorted(entity_ids)),
        ).fetchall()
        entities = {str(row["entity_id"]): dict(row) for row in entity_rows}

    aliases: dict[str, dict] = {}
    alias_group_ids = {
        _clean(entity.get("alias_group_id"))
        for entity in entities.values()
        if _clean(entity.get("alias_group_id"))
    }
    if alias_group_ids:
        placeholders = ",".join("?" for _ in alias_group_ids)
        alias_rows = conn.execute(
            f"""
            SELECT alias_group_id, canonical_name, aliases_json, entity_type,
                   story_id, worldline_id, metadata_json
            FROM entity_alias_groups
            WHERE alias_group_id IN ({placeholders}) AND deleted_at IS NULL
            """,
            tuple(sorted(alias_group_ids)),
        ).fetchall()
        for row in alias_rows:
            value = dict(row)
            try:
                value["aliases"] = json.loads(value.pop("aliases_json") or "[]")
            except (TypeError, ValueError):
                value["aliases"] = []
            try:
                value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
            except (TypeError, ValueError):
                value["metadata"] = {}
            aliases[str(value.get("alias_group_id") or "")] = value

    evidence: dict[str, list[dict]] = {knowledge_id: [] for knowledge_id in knowledge_ids}
    if knowledge_ids:
        placeholders = ",".join("?" for _ in knowledge_ids)
        evidence_rows = conn.execute(
            f"""
            SELECT evidence_id, knowledge_id, pending_id, source_id, segment_id,
                   chunk_id, quote, location_json, confidence, evidence_strength,
                   created_at
            FROM knowledge_evidence WHERE knowledge_id IN ({placeholders})
            ORDER BY created_at, evidence_id
            """,
            tuple(knowledge_ids),
        ).fetchall()
        for row in evidence_rows:
            value = dict(row)
            try:
                value["location"] = json.loads(value.pop("location_json") or "{}")
            except (TypeError, ValueError):
                value["location"] = {}
            evidence.setdefault(_clean(value.get("knowledge_id")), []).append(value)

    relations: dict[str, list[dict]] = {entity_id: [] for entity_id in entity_ids}
    owned_relations: dict[str, list[dict]] = {}
    if edge_rows:
        for row in edge_rows:
            value = dict(row)
            try:
                value["metadata"] = json.loads(value.pop("metadata_json") or "{}")
            except (TypeError, ValueError):
                value["metadata"] = {}
            owner_id = _clean(value["metadata"].get("knowledge_id"))
            owned_relations.setdefault(owner_id, []).append(value)
            source = _clean(value.get("source_node_id"))
            target = _clean(value.get("target_node_id"))
            if source in relations:
                relations[source].append(value)
            if target in relations and target != source:
                relations[target].append(value)

    for item in result:
        knowledge_id = _clean(item.get("knowledge_id") or item.get("id"))
        entity_id = _clean(item.get("entity_id"))
        entity = entities.get(entity_id)
        if entity:
            item.setdefault("canonical_name", entity.get("canonical_name") or "")
            item.setdefault("entity_type", entity.get("entity_type") or "")
            item["entity"] = entity
            alias = aliases.get(_clean(entity.get("alias_group_id")))
            item["entity_aliases"] = list((alias or {}).get("aliases") or [])
            item["entity_alias_group"] = alias or {}
        item_edges = {
            edge["edge_id"]: edge
            for edge in [*relations.get(entity_id, []), *owned_relations.get(knowledge_id, [])]
        }
        item["entity_relations"] = list(item_edges.values())
        endpoint_ids = {
            _clean(edge.get(key)) for edge in item_edges.values()
            for key in ("source_node_id", "target_node_id")
        }
        item["related_entities"] = [
            {**entities[endpoint_id],
             "aliases": list((aliases.get(_clean(entities[endpoint_id].get("alias_group_id"))) or {}).get("aliases") or [])}
            for endpoint_id in sorted(endpoint_ids) if endpoint_id in entities
        ]
        item["evidence"] = evidence.get(knowledge_id, [])
    return result


def _fragment_snapshot_rows(conn: sqlite3.Connection, branch_id: str, frontier_fragment_id: str | None = None) -> list[dict]:
    # The parent chain, rather than timestamp order, defines the readable
    # prefix. A missing/foreign frontier is an error; silently falling back to
    # every fragment would leak future branches into a historical checkpoint.
    current = _clean(frontier_fragment_id)
    if not current:
        row = conn.execute(
            """
            SELECT fragment_id FROM creative_fragments
            WHERE branch_id = ? AND status IN ('accepted', 'finalized')
              AND NOT EXISTS (
                  SELECT 1 FROM creative_fragments AS child
                  WHERE child.branch_id = creative_fragments.branch_id
                    AND child.parent_fragment_id = creative_fragments.fragment_id
                    AND child.status IN ('accepted', 'finalized')
              )
            ORDER BY COALESCE(accepted_at, created_at) DESC, fragment_id DESC LIMIT 1
            """,
            (branch_id,),
        ).fetchone()
        current = _clean(row[0]) if row else ""
    chain: list[str] = []
    seen: set[str] = set()
    while current:
        if current in seen:
            raise ValueError("Creative fragment chain contains a cycle.")
        seen.add(current)
        row = conn.execute(
            """
            SELECT fragment_id, parent_fragment_id, branch_id, status
            FROM creative_fragments WHERE fragment_id = ?
            """,
            (current,),
        ).fetchone()
        if row is None or _clean(row["branch_id"]) != branch_id:
            raise ValueError("Fork frontier fragment does not belong to the branch.")
        if str(row["status"] or "") not in {"accepted", "finalized"}:
            raise ValueError("Fork frontier must be an accepted fragment.")
        chain.append(str(row["fragment_id"]))
        current = _clean(row["parent_fragment_id"])
    if not chain:
        return []
    placeholders = ",".join("?" for _ in chain)
    rows = conn.execute(
        f"""
        SELECT fragment_id, session_id, turn_id, parent_fragment_id, content,
               status, content_hash, word_count, context_snapshot_id,
               extraction_status, created_at, accepted_at, branch_id
        FROM creative_fragments WHERE branch_id = ? AND fragment_id IN ({placeholders})
        """,
        (branch_id, *chain),
    ).fetchall()
    by_id = {str(row["fragment_id"]): dict(row) for row in rows}
    return [by_id[item] for item in reversed(chain) if item in by_id]


def create_checkpoint_row(
    conn: sqlite3.Connection,
    *,
    branch_id: str,
    frontier_fragment_id: str | None = None,
    extraction_status: str = "ready",
    reason: str = "",
    checkpoint_id: str | None = None,
    allow_current_state: bool = False,
    configuration_snapshot: dict | None = None,
) -> dict:
    branch = load_branch_row(conn, branch_id)
    if branch is None:
        raise ValueError("Branch does not exist.")
    story_id = str(branch["story_id"])
    previous = conn.execute(
        "SELECT checkpoint_id, revision FROM branch_checkpoints WHERE branch_id = ? ORDER BY revision DESC LIMIT 1",
        (branch_id,),
    ).fetchone()
    requested_frontier = _clean(frontier_fragment_id)
    if requested_frontier:
        captured = conn.execute(
            "SELECT checkpoint_id FROM branch_checkpoints WHERE branch_id = ? AND frontier_fragment_id = ? ORDER BY revision DESC LIMIT 1",
            (branch_id, requested_frontier),
        ).fetchone()
        if captured:
            source = load_checkpoint_row(conn, str(captured[0])) or {}
            source_status = str(source.get("extraction_status") or "ready")
            requested_status = _clean(extraction_status) or "ready"
            if source_status in {"ready", "completed", "skipped"} or requested_status == source_status:
                return source
            # A pending capture can only become a ready/skipped immutable copy
            # of the same payload. Never rebuild it from today's live rows.
            if source_status == "pending" and requested_status in {"ready", "completed", "skipped"}:
                revision = int(previous["revision"] if previous else 0) + 1
                new_id = _clean(checkpoint_id) or f"checkpoint_{uuid4().hex}"
                now = _now()
                manifest = dict(source.get("snapshot_manifest") or {})
                # 提炼可能在 F2 已经写入后才完成。只把明确锚定到本次
                # frontier 的新确认知识补进封存快照，不能把当时已经存在的
                # F2 或其它片段知识一起带入历史分叉。
                base_knowledge = [
                    dict(item) for item in (manifest.get("knowledge") or [])
                    if isinstance(item, dict)
                ]
                base_ids = {
                    str(item.get("knowledge_id") or item.get("id") or "")
                    for item in base_knowledge
                }
                late_items: list[dict] = []
                for item in _knowledge_snapshot_rows(conn, story_id, branch_id):
                    item_id = str(item.get("knowledge_id") or item.get("id") or "")
                    if not item_id or item_id in base_ids:
                        continue
                    source_fragment = str(item.get("source_segment_id") or "")
                    source_fragments = item.get("source_segment_ids")
                    if isinstance(source_fragments, str):
                        try:
                            source_fragments = json.loads(source_fragments)
                        except (TypeError, ValueError):
                            source_fragments = []
                    if not isinstance(source_fragments, list):
                        source_fragments = []
                    content_json = item.get("content_json")
                    if isinstance(content_json, str):
                        try:
                            content_payload = json.loads(content_json)
                        except (TypeError, ValueError):
                            content_payload = {}
                    else:
                        content_payload = content_json if isinstance(content_json, dict) else {}
                    source_fragment = source_fragment or str(content_payload.get("source_segment_id") or "")
                    source_fragments = [
                        *[str(value) for value in source_fragments],
                        *[
                            str(value)
                            for value in (content_payload.get("source_segment_ids") or [])
                            if str(value)
                        ],
                    ]
                    if source_fragment != requested_frontier and requested_frontier not in source_fragments:
                        continue
                    late_items.append(dict(item))
                if late_items:
                    manifest["knowledge"] = [*base_knowledge, *late_items]
                canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                manifest_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                conn.execute(
                    """
                    INSERT INTO branch_checkpoints (
                        checkpoint_id, branch_id, parent_checkpoint_id, revision,
                        frontier_fragment_id, frontier_content_hash, baseline_revision,
                        snapshot_manifest_json, snapshot_hash, extraction_status, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        new_id, branch_id, source.get("checkpoint_id"), revision,
                        source.get("frontier_fragment_id"), source.get("frontier_content_hash") or "",
                        source.get("baseline_revision") or 0,
                        canonical,
                        manifest_hash,
                        requested_status,
                        _clean(reason) or "从已捕获基线确认", now,
                    ),
                )
                rows = conn.execute(
                    "SELECT item_kind, item_id, item_revision_id, origin_id, state, ordinal, payload_json FROM branch_checkpoint_items WHERE checkpoint_id = ?",
                    (source.get("checkpoint_id"),),
                ).fetchall()
                for row in rows:
                    conn.execute(
                        """
                        INSERT INTO branch_checkpoint_items
                            (checkpoint_id, item_kind, item_id, item_revision_id, origin_id, state, ordinal, payload_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (new_id, row["item_kind"], row["item_id"], row["item_revision_id"], row["origin_id"], row["state"], row["ordinal"], row["payload_json"]),
                    )
                if late_items:
                    ordinal = max((int(row["ordinal"] or 0) for row in rows), default=-1) + 1
                    for item in late_items:
                        item_id = str(item.get("knowledge_id") or item.get("id") or "")
                        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
                        conn.execute(
                            """
                            INSERT INTO branch_checkpoint_items
                                (checkpoint_id, item_kind, item_id, item_revision_id, origin_id, state, ordinal, payload_json)
                            VALUES (?, 'knowledge', ?, ?, ?, 'local', ?, ?)
                            """,
                            (
                                new_id,
                                item_id,
                                _clean(item.get("revision_id")),
                                _clean(item.get("origin_knowledge_id")) or item_id,
                                ordinal,
                                payload,
                            ),
                        )
                        ordinal += 1
                conn.execute(
                    "UPDATE story_branches SET head_checkpoint_id = ?, revision = ?, updated_at = ? WHERE branch_id = ?",
                    (new_id, revision, now, branch_id),
                )
                return load_checkpoint_row(conn, new_id) or {}
        elif previous and not allow_current_state:
            current_rows = _fragment_snapshot_rows(conn, branch_id)
            current_frontier = str(current_rows[-1].get("fragment_id") or "") if current_rows else ""
            if current_frontier and current_frontier != requested_frontier:
                raise ValueError("指定的旧 frontier 没有该时点的可靠检查点；请先完成当前基线，或明确 allow_current_state。")
    revision = int(previous["revision"] if previous else 0) + 1
    parent_checkpoint_id = str(previous["checkpoint_id"]) if previous else None
    fragments = _fragment_snapshot_rows(conn, branch_id, frontier_fragment_id)
    knowledge = _knowledge_snapshot_rows(conn, story_id, branch_id)
    # A child branch starts with immutable inherited payloads. A later child
    # checkpoint must carry those forward even though the live knowledge table
    # only contains rows physically owned by the child. Local rows may carry
    # origin_knowledge_id and then replace the inherited payload at that ID.
    if previous:
        previous_checkpoint = load_checkpoint_row(conn, str(previous["checkpoint_id"])) or {}
        previous_knowledge = [
            dict(item)
            for item in (previous_checkpoint.get("snapshot_manifest") or {}).get("knowledge", [])
            if isinstance(item, dict)
        ]
        merged_knowledge = {
            str(item.get("knowledge_id") or item.get("id") or ""): item
            for item in previous_knowledge
            if str(item.get("knowledge_id") or item.get("id") or "")
        }
        for item in knowledge:
            item_id = str(item.get("knowledge_id") or item.get("id") or "")
            if not item_id:
                continue
            origin_id = _knowledge_origin_id(item)
            if origin_id:
                item = dict(item)
                item["origin_knowledge_id"] = origin_id
            merged_knowledge[origin_id or item_id] = item
        knowledge = list(merged_knowledge.values())
    configured_story_rules = (
        configuration_snapshot.get("story_rules")
        if isinstance(configuration_snapshot, dict)
        else None
    )
    if isinstance(configured_story_rules, dict):
        # Branch overlays are part of the captured configuration baseline. Do
        # not replace them with the mutable story-level rules table while the
        # parent checkpoint is being materialized.
        story_rules = {
            str(capability): [str(content) for content in (contents or [])]
            for capability, contents in configured_story_rules.items()
            if isinstance(contents, list)
        }
    else:
        rule_rows = conn.execute(
            """
            SELECT capability, content FROM rules
            WHERE scope = 'story' AND story_id = ? AND deleted_at IS NULL AND enabled = 1
            ORDER BY capability, priority, created_at, rule_id
            """,
            (story_id,),
        ).fetchall()
        story_rules = {}
        for row in rule_rows:
            story_rules.setdefault(str(row["capability"]), []).append(str(row["content"]))
    items = {
        "knowledge": knowledge,
        "fragments": fragments,
        "story_rules": story_rules,
        "configuration": dict(configuration_snapshot or {}),
        "branch_id": branch_id,
        "story_id": story_id,
    }
    if allow_current_state:
        reason = _clean(reason) or "明确允许的当前状态变体"
        if "当前状态" not in reason:
            reason = f"当前状态变体：{reason}"
    canonical = json.dumps(items, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    snapshot_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    checkpoint_id = _clean(checkpoint_id) or f"checkpoint_{uuid4().hex}"
    frontier_hash = ""
    if frontier_fragment_id:
        row = conn.execute("SELECT content_hash FROM creative_fragments WHERE fragment_id = ?", (frontier_fragment_id,)).fetchone()
        frontier_hash = _clean(row[0]) if row else ""
    now = _now()
    conn.execute(
        """
        INSERT INTO branch_checkpoints (
            checkpoint_id, branch_id, parent_checkpoint_id, revision,
            frontier_fragment_id, frontier_content_hash, baseline_revision,
            snapshot_manifest_json, snapshot_hash, extraction_status, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            checkpoint_id, branch_id, parent_checkpoint_id, revision,
            _clean(frontier_fragment_id) or None, frontier_hash, int(branch["revision"] or 0),
            canonical, snapshot_hash, _clean(extraction_status) or "ready", _clean(reason), now,
        ),
    )
    for ordinal, item in enumerate(knowledge):
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        conn.execute(
            """
            INSERT INTO branch_checkpoint_items (
                checkpoint_id, item_kind, item_id, item_revision_id,
                origin_id, state, ordinal, payload_json
            ) VALUES (?, 'knowledge', ?, ?, ?, 'local', ?, ?)
            """,
            (
                checkpoint_id, str(item["knowledge_id"]), _clean(item.get("revision_id")),
                _clean(item.get("origin_knowledge_id")) or str(item["knowledge_id"]), ordinal, payload,
            ),
        )
    for ordinal, item in enumerate(fragments):
        payload = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str)
        conn.execute(
            """
            INSERT INTO branch_checkpoint_items (
                checkpoint_id, item_kind, item_id, state, ordinal, payload_json
            ) VALUES (?, 'fragment', ?, 'local', ?, ?)
            """,
            (checkpoint_id, str(item["fragment_id"]), ordinal, payload),
        )
    conn.execute(
        """
        UPDATE story_branches
        SET head_checkpoint_id = ?, revision = ?, updated_at = ?
        WHERE branch_id = ?
        """,
        (checkpoint_id, revision, now, branch_id),
    )
    return load_checkpoint_row(conn, checkpoint_id) or {}


def fork_branch_rows(
    conn: sqlite3.Connection,
    *,
    story_id: str,
    parent_branch_id: str,
    name: str,
    description: str = "",
    fork_checkpoint_id: str | None = None,
    fork_fragment_id: str | None = None,
    branch_id: str | None = None,
    allow_current_state: bool = False,
    configuration_snapshot: dict | None = None,
) -> dict:
    parent = load_branch_for_story(conn, story_id, parent_branch_id)
    if parent["status"] != "active":
        raise ValueError("Cannot fork from an archived branch.")
    checkpoint_id = _clean(fork_checkpoint_id)
    # ``allow_current_state`` explicitly opts into a new capture of the
    # parent's current state.  Reusing its existing head here would silently
    # discard branch configuration edits made after that head was frozen.
    # An explicit checkpoint/fragment remains an historical anchor and is
    # therefore resolved below as requested.
    capture_current_state = bool(allow_current_state and not checkpoint_id and not _clean(fork_fragment_id))
    if capture_current_state:
        checkpoint = create_checkpoint_row(
            conn,
            branch_id=parent_branch_id,
            reason="用户明确以当前状态创建变体",
            allow_current_state=True,
            configuration_snapshot=configuration_snapshot,
        )
        checkpoint_id = checkpoint["checkpoint_id"]
    elif checkpoint_id:
        checkpoint = load_checkpoint_row(conn, checkpoint_id)
    elif fork_fragment_id:
        checkpoint = None
        candidate_rows = conn.execute(
            "SELECT checkpoint_id FROM branch_checkpoints WHERE branch_id = ? AND extraction_status IN ('ready', 'completed', 'skipped') ORDER BY revision DESC",
            (parent_branch_id,),
        ).fetchall()
        for candidate in candidate_rows:
            candidate_checkpoint = load_checkpoint_row(conn, str(candidate[0]))
            if candidate_checkpoint is None:
                continue
            if _clean(candidate_checkpoint.get("frontier_fragment_id")) == _clean(fork_fragment_id):
                checkpoint = candidate_checkpoint
                checkpoint_id = candidate_checkpoint["checkpoint_id"]
                break
    else:
        checkpoint_id = _clean(parent.get("head_checkpoint_id"))
        checkpoint = load_checkpoint_row(conn, checkpoint_id) if checkpoint_id else None
    if checkpoint is None:
        if not allow_current_state:
            raise ValueError("该分叉锚点尚无可靠检查点，请先完成正文确认/提炼，或明确选择以当前状态创建变体。")
        checkpoint = create_checkpoint_row(
            conn,
            branch_id=parent_branch_id,
            frontier_fragment_id=fork_fragment_id,
            reason="用户明确以当前状态创建变体",
            allow_current_state=True,
            configuration_snapshot=configuration_snapshot,
        )
        checkpoint_id = checkpoint["checkpoint_id"]
    if checkpoint["branch_id"] != parent_branch_id:
        raise ValueError("Fork checkpoint does not belong to parent branch.")
    if str(checkpoint.get("extraction_status") or "ready") not in {"ready", "completed", "skipped"}:
        raise ValueError("该检查点尚未 ready，不能作为世界线分叉锚点。")
    if fork_fragment_id:
        if _clean(checkpoint.get("frontier_fragment_id")) != _clean(fork_fragment_id):
            raise ValueError("所选检查点前沿与分叉片段不一致，不能用更晚状态替代。")
    child = create_branch_row(
        conn,
        story_id=story_id,
        name=name,
        description=description,
        parent_branch_id=parent_branch_id,
        fork_fragment_id=fork_fragment_id or checkpoint.get("frontier_fragment_id"),
        fork_checkpoint_id=checkpoint_id,
        source_worldline_id=str(parent.get("source_worldline_id") or "main"),
        branch_id=branch_id,
    )
    child_checkpoint_id = f"checkpoint_{uuid4().hex}"
    child_revision = 1
    conn.execute(
        """
        INSERT INTO branch_checkpoints (
            checkpoint_id, branch_id, parent_checkpoint_id, revision,
            frontier_fragment_id, frontier_content_hash, baseline_revision,
            snapshot_manifest_json, snapshot_hash, extraction_status, reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            child_checkpoint_id, child["branch_id"], checkpoint_id, child_revision,
            checkpoint.get("frontier_fragment_id"), checkpoint.get("frontier_content_hash") or "",
            checkpoint.get("baseline_revision") or 0,
            json.dumps(checkpoint.get("snapshot_manifest") or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            checkpoint.get("snapshot_hash") or "", checkpoint.get("extraction_status") or "ready",
            "从父线固定检查点创建世界线",
        ),
    )
    # The snapshot rows are immutable payloads. Copy them into the child so
    # subsequent parent edits cannot alter the child baseline.
    source_items = conn.execute(
        "SELECT item_kind, item_id, item_revision_id, origin_id, state, ordinal, payload_json FROM branch_checkpoint_items WHERE checkpoint_id = ? ORDER BY item_kind, ordinal, item_id",
        (checkpoint_id,),
    ).fetchall()
    for row in source_items:
        conn.execute(
            """
            INSERT INTO branch_checkpoint_items (
                checkpoint_id, item_kind, item_id, item_revision_id,
                origin_id, state, ordinal, payload_json
            ) VALUES (?, ?, ?, ?, ?, 'inherited', ?, ?)
            """,
            (
                child_checkpoint_id, row["item_kind"], row["item_id"],
                row["item_revision_id"], row["origin_id"], row["ordinal"], row["payload_json"],
            ),
        )
        if row["item_kind"] == "fragment":
            payload = json.loads(row["payload_json"] or "{}")
            conn.execute(
                """
                INSERT OR IGNORE INTO branch_fragment_states (
                    branch_id, fragment_id, checkpoint_id, state, ordinal,
                    source_branch_id, content_hash
                ) VALUES (?, ?, ?, 'inherited', ?, ?, ?)
                """,
                (
                    child["branch_id"], row["item_id"], child_checkpoint_id,
                    row["ordinal"], parent_branch_id, _clean(payload.get("content_hash")),
                ),
            )
    # The child checkpoint is still the exact immutable parent payload. Keep
    # its manifest/hash unchanged and point the branch at it.
    conn.execute(
        "UPDATE story_branches SET head_checkpoint_id = ?, fork_checkpoint_id = ?, revision = ? WHERE branch_id = ?",
        (child_checkpoint_id, checkpoint_id, child_revision, child["branch_id"]),
    )
    return load_branch_row(conn, child["branch_id"]) or {}


def clone_checkpoint_fragments_to_session(
    conn: sqlite3.Connection,
    *,
    checkpoint_id: str,
    child_branch_id: str,
    session_id: str,
) -> dict:
    """Materialize the immutable prefix into the child writing session.

    Session rows are mutable workflow state, so a child session gets fresh
    fragment/turn IDs while the checkpoint retains the parent IDs as origin
    references. This lets the child continue immediately without sharing
    acceptance or finalized status with its ancestor.
    """
    rows = conn.execute(
        """
        SELECT item_id, ordinal, payload_json
        FROM branch_checkpoint_items
        WHERE checkpoint_id = ? AND item_kind = 'fragment'
        ORDER BY ordinal, item_id
        """,
        (_clean(checkpoint_id),),
    ).fetchall()
    if not rows:
        return {"fragment_id": None, "fragment_map": {}}
    fragment_map: dict[str, str] = {}
    turn_map: dict[str, str] = {}
    now = _now()
    for ordinal, row in enumerate(rows, start=1):
        payload = json.loads(row["payload_json"] or "{}")
        old_fragment_id = _clean(row["item_id"])
        new_fragment_id = f"fragment_{uuid4().hex}"
        old_turn_id = _clean(payload.get("turn_id"))
        new_turn_id = f"turn_{uuid4().hex}"
        fragment_map[old_fragment_id] = new_fragment_id
        if old_turn_id:
            turn_map[old_turn_id] = new_turn_id
    last_fragment_id: str | None = None
    for ordinal, row in enumerate(rows, start=1):
        payload = json.loads(row["payload_json"] or "{}")
        old_fragment_id = _clean(row["item_id"])
        new_fragment_id = fragment_map[old_fragment_id]
        old_turn_id = _clean(payload.get("turn_id"))
        new_turn_id = turn_map.get(old_turn_id, f"turn_{uuid4().hex}")
        old_parent = _clean(payload.get("parent_fragment_id"))
        new_parent = fragment_map.get(old_parent) or None
        source_turn = conn.execute(
            "SELECT user_message, action_type FROM creative_turns WHERE turn_id = ?",
            (old_turn_id,),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO creative_turns (
                turn_id, session_id, branch_id, turn_index, user_message,
                action_type, parent_fragment_id, status, error_text, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'completed', '', ?, ?)
            """,
            (
                new_turn_id, session_id, child_branch_id, ordinal,
                str(source_turn["user_message"] if source_turn else "继承前线正文"),
                str(source_turn["action_type"] if source_turn else "continue"),
                new_parent, now, now,
            ),
        )
        conn.execute(
            """
            INSERT INTO creative_fragments (
                fragment_id, session_id, branch_id, turn_id, parent_fragment_id,
                content, status, content_hash, word_count, context_snapshot_id,
                extraction_status, created_at, accepted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_fragment_id, session_id, child_branch_id, new_turn_id, new_parent,
                str(payload.get("content") or ""), str(payload.get("status") or "accepted"),
                str(payload.get("content_hash") or ""), int(payload.get("word_count") or 0),
                payload.get("context_snapshot_id"), str(payload.get("extraction_status") or "completed"),
                now, payload.get("accepted_at") or now,
            ),
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO branch_fragment_states (
                branch_id, fragment_id, checkpoint_id, state, ordinal,
                source_branch_id, content_hash
            ) VALUES (?, ?, ?, 'inherited', ?,
                (SELECT story_branches.parent_branch_id FROM story_branches WHERE story_branches.branch_id = ?), ?)
            """,
            (
                child_branch_id, new_fragment_id, checkpoint_id, ordinal,
                child_branch_id, str(payload.get("content_hash") or ""),
            ),
        )
        last_fragment_id = new_fragment_id
    conn.execute(
        "UPDATE creative_sessions SET active_fragment_id = ?, updated_at = ? WHERE session_id = ?",
        (last_fragment_id, now, session_id),
    )
    return {"fragment_id": last_fragment_id, "fragment_map": fragment_map}


def resolve_branch_context_row(
    conn: sqlite3.Connection,
    story_id: str,
    branch_id: str,
    *,
    configuration_snapshot: dict | None = None,
) -> dict:
    branch = load_branch_for_story(conn, story_id, branch_id)
    checkpoint_id = _clean(branch.get("head_checkpoint_id"))
    checkpoint = load_checkpoint_row(conn, checkpoint_id) if checkpoint_id else None
    if checkpoint is None:
        checkpoint = create_checkpoint_row(
            conn,
            branch_id=branch_id,
            reason="建立默认分支检查点",
            configuration_snapshot=configuration_snapshot,
        )
    items = conn.execute(
        "SELECT item_kind, item_id, item_revision_id, origin_id, state, ordinal, payload_json FROM branch_checkpoint_items WHERE checkpoint_id = ? ORDER BY item_kind, ordinal, item_id",
        (checkpoint["checkpoint_id"],),
    ).fetchall()
    manifest_items: list[dict] = []
    for row in items:
        item = dict(row)
        try:
            item["payload"] = json.loads(item.pop("payload_json") or "{}")
        except (TypeError, ValueError):
            item["payload"] = {}
        manifest_items.append(item)
    frozen_ids = {
        str(item.get("item_id") or "")
        for item in manifest_items
        if str(item.get("item_kind") or "") == "knowledge"
    }
    local_knowledge_items: list[dict] = []
    for item in _knowledge_snapshot_rows(conn, story_id, branch_id, include_deleted=True):
        item_id = str(item.get("knowledge_id") or item.get("id") or "")
        origin_id = _knowledge_origin_id(item)
        if origin_id and origin_id in frozen_ids:
            copied = dict(item)
            copied["origin_knowledge_id"] = origin_id
            local_knowledge_items.append(copied)
        elif item_id not in frozen_ids or str(item.get("branch_id") or "") == branch_id:
            local_knowledge_items.append(item)
    return {
        "story_id": story_id,
        "branch_id": branch_id,
        "checkpoint_id": checkpoint["checkpoint_id"],
        "frontier_id": checkpoint.get("frontier_fragment_id"),
        "baseline_revision": int(checkpoint.get("baseline_revision") or 0),
        "visible_revision_manifest": manifest_items,
        "local_knowledge_payloads": local_knowledge_items,
        "story_rules": ((checkpoint.get("snapshot_manifest") or {}).get("story_rules") or {}),
        "configuration": ((checkpoint.get("snapshot_manifest") or {}).get("configuration") or {}),
        "snapshot_hash": checkpoint.get("snapshot_hash") or "",
        "extraction_status": checkpoint.get("extraction_status") or "ready",
        "source_worldline_id": branch.get("source_worldline_id") or "main",
        "branch": branch,
    }
