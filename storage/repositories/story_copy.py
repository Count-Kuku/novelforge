from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import PurePosixPath
from typing import Any

from .creative_sessions import clone_creative_session_rows
from .branches import default_branch_id
from .entity_identity import entity_id_for


def _copy_scoped_id(prefix: str, target_story_id: str, source_id: str) -> str:
    digest = hashlib.sha256(f"{target_story_id}:{source_id}".encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _branch_folder(branch_id: str) -> str:
    clean = str(branch_id or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", clean)
    return f"{slug[:48]}_{hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]}"


_CHAPTER_ASSET_TYPES = {
    "chapter_outline",
    "chapter_outline_metadata",
    "chapter_discussion",
    "chapter",
    "review_markdown",
    "review_json",
    "analysis_markdown",
    "evaluation_markdown",
    "evaluation_json",
    "workflow_run_snapshot",
    "generation_context_snapshot",
}

_DISCUSSION_ASSET_TYPES = {
    "creative_profile_discussion",
    "outline_discussion",
    "chapter_discussion",
    "volume_discussion",
    "arc_discussion",
}

_VOLUME_ARC_ASSET_TYPES = {
    "volume_outline",
    "volume_metadata",
    "volume_discussion",
    "arc_outline",
    "arc_metadata",
    "arc_discussion",
    "arc_chapter_plan",
}

_PATH_FIELD_NAMES = {
    "directory",
    "directories",
    "dir_path",
    "dir_paths",
    "file_path",
    "file_paths",
    "filepath",
    "filepaths",
    "path",
    "paths",
}


def _is_path_field(key: str) -> bool:
    snake_key = re.sub(r"(?<!^)(?=[A-Z])", "_", str(key or ""))
    snake_key = re.sub(r"[^a-zA-Z0-9]+", "_", snake_key).strip("_").lower()
    return (
        snake_key in _PATH_FIELD_NAMES
        or snake_key.endswith("_path")
        or snake_key.endswith("_paths")
    )


def _rewrite_story_path_string(
    value: str,
    *,
    source_story_id: str,
    target_story_id: str,
    explicit_path_field: bool,
) -> str:
    """Rewrite an exact story directory segment in path-like strings only.

    An explicit path field may contain spaces. Outside such a field, the value
    must look like a standalone path (no whitespace), which keeps prose such as
    ``see stories/source/chapter.md`` unchanged.
    """

    if not explicit_path_field and any(char.isspace() for char in value):
        return value
    pattern = re.compile(
        rf"(?P<prefix>^|[\\/])stories(?P<story_sep>[\\/])"
        rf"{re.escape(source_story_id)}(?P<tail_sep>[\\/])"
    )
    if not pattern.search(value):
        return value
    return pattern.sub(
        lambda match: (
            f"{match.group('prefix')}stories{match.group('story_sep')}"
            f"{target_story_id}{match.group('tail_sep')}"
        ),
        value,
    )


def _active_story_exists(conn: sqlite3.Connection, story_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM stories WHERE story_id = ? AND deleted_at IS NULL",
        (story_id,),
    ).fetchone() is not None


def _copy_run_id(conn: sqlite3.Connection, source_run_id: str, target_story_id: str) -> str:
    digest = hashlib.sha256(f"{target_story_id}:{source_run_id}".encode("utf-8")).hexdigest()[:10]
    safe_source = "".join(
        char if (char.isalnum() or char in {"_", "-", "."}) else "_"
        for char in source_run_id
    ).strip(".")
    safe_source = safe_source[:96] or "workflow_run"
    base = f"{safe_source}__copy_{digest}"
    candidate = base
    counter = 2
    while conn.execute("SELECT 1 FROM workflow_runs WHERE run_id = ?", (candidate,)).fetchone():
        candidate = f"{base}_{counter}"
        counter += 1
    return candidate


def _rewrite_structured_value(
    value: Any,
    *,
    source_story_id: str,
    target_story_id: str,
    run_id_map: dict[str, str],
    asset_id_map: dict[str, str],
    branch_id_map: dict[str, str] | None = None,
    session_id_map: dict[str, str] | None = None,
    turn_id_map: dict[str, str] | None = None,
    fragment_id_map: dict[str, str] | None = None,
    knowledge_id_map: dict[str, str] | None = None,
    binding_id_map: dict[str, str] | None = None,
    checkpoint_id_map: dict[str, str] | None = None,
    entity_id_map: dict[str, str] | None = None,
    _path_context: bool = False,
) -> Any:
    if isinstance(value, list):
        return [
            _rewrite_structured_value(
                item,
                source_story_id=source_story_id,
                target_story_id=target_story_id,
                run_id_map=run_id_map,
                asset_id_map=asset_id_map,
                branch_id_map=branch_id_map,
                session_id_map=session_id_map,
                turn_id_map=turn_id_map,
                fragment_id_map=fragment_id_map,
                knowledge_id_map=knowledge_id_map,
                binding_id_map=binding_id_map,
                checkpoint_id_map=checkpoint_id_map,
                entity_id_map=entity_id_map,
                _path_context=_path_context,
            )
            for item in value
        ]
    if isinstance(value, str):
        return _rewrite_story_path_string(
            value,
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            explicit_path_field=_path_context,
        )
    if not isinstance(value, dict):
        return value

    rewritten: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key)
        nested = _rewrite_structured_value(
            raw_value,
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            run_id_map=run_id_map,
            asset_id_map=asset_id_map,
            branch_id_map=branch_id_map,
            session_id_map=session_id_map,
            turn_id_map=turn_id_map,
            fragment_id_map=fragment_id_map,
            knowledge_id_map=knowledge_id_map,
            binding_id_map=binding_id_map,
            checkpoint_id_map=checkpoint_id_map,
            entity_id_map=entity_id_map,
            _path_context=_is_path_field(key),
        )
        if key == "story_id" and nested == source_story_id:
            nested = target_story_id
        elif key in {"run_id", "parent_run_id"} and isinstance(nested, str):
            nested = run_id_map.get(nested, nested)
        elif (key.endswith("asset_id") or key == "context_snapshot_id") and isinstance(nested, str):
            nested = asset_id_map.get(nested, nested)
        elif key == "branch_id" and isinstance(nested, str):
            nested = (branch_id_map or {}).get(nested, nested)
        elif key == "session_id" and isinstance(nested, str):
            nested = (session_id_map or {}).get(nested, nested)
        elif key in {"turn_id", "parent_turn_id"} and isinstance(nested, str):
            nested = (turn_id_map or {}).get(nested, nested)
        elif key in {"fragment_id", "parent_fragment_id", "frontier_fragment_id"} and isinstance(nested, str):
            nested = (fragment_id_map or {}).get(nested, nested)
        elif key in {"knowledge_id", "origin_knowledge_id", "local_knowledge_id", "promoted_knowledge_id"} and isinstance(nested, str):
            nested = (knowledge_id_map or {}).get(nested, nested)
        elif key in {"binding_id", "story_library_binding_id"} and isinstance(nested, str):
            nested = (binding_id_map or {}).get(nested, nested)
        elif key in {"checkpoint_id", "parent_checkpoint_id", "head_checkpoint_id", "fork_checkpoint_id"} and isinstance(nested, str):
            nested = (checkpoint_id_map or {}).get(nested, nested)
        elif key in {"entity_id", "origin_entity_id", "local_entity_id", "source_node_id", "target_node_id"} and isinstance(nested, str):
            nested = (entity_id_map or {}).get(nested, nested)
        rewritten[key] = nested
    return rewritten


def _rewrite_json_text(
    raw: Any,
    *,
    source_story_id: str,
    target_story_id: str,
    run_id_map: dict[str, str],
    asset_id_map: dict[str, str],
    **maps: dict[str, str] | None,
) -> str:
    text = str(raw or "")
    try:
        parsed = json.loads(text)
    except Exception:
        return text
    rewritten = _rewrite_structured_value(
        parsed,
        source_story_id=source_story_id,
        target_story_id=target_story_id,
        run_id_map=run_id_map,
        asset_id_map=asset_id_map,
        **maps,
    )
    return json.dumps(rewritten, ensure_ascii=False, sort_keys=True)


def _asset_is_included(
    asset_type: str,
    *,
    include_discussions: bool,
    include_summaries: bool,
    include_chapters: bool,
) -> bool:
    if not include_chapters and asset_type in _CHAPTER_ASSET_TYPES:
        return False
    if not include_summaries and asset_type == "chapter_summaries":
        return False
    if not include_discussions and (
        asset_type in _DISCUSSION_ASSET_TYPES or asset_type in _VOLUME_ARC_ASSET_TYPES
    ):
        return False
    return True


def _target_relative_path(
    relative_path: str,
    *,
    source_story_id: str,
    target_story_id: str,
    source_run_id: str = "",
    target_run_id: str = "",
    branch_id_map: dict[str, str] | None = None,
) -> str:
    normalized = str(relative_path or "").replace("\\", "/")
    source_path = PurePosixPath(normalized)
    source_parts = source_path.parts
    if (
        source_path.is_absolute()
        or any(part in {"", ".", ".."} or ":" in part for part in source_parts)
        or len(source_parts) < 3
        or source_parts[:2] != ("stories", source_story_id)
    ):
        raise ValueError(f"Story asset path is outside its story directory: {relative_path}")

    target_parts = ["stories", target_story_id, *source_parts[2:]]
    if len(target_parts) >= 5 and target_parts[2] == "branches":
        source_branch_folder = target_parts[3]
        for source_branch_id, target_branch_id in (branch_id_map or {}).items():
            if _branch_folder(source_branch_id) == source_branch_folder:
                target_parts[3] = _branch_folder(target_branch_id)
                break
    if (
        source_run_id
        and target_run_id
        and len(target_parts) >= 4
        and target_parts[-2] == "runs"
        and target_parts[-1] == f"{source_run_id}.json"
    ):
        target_parts[-1] = f"{target_run_id}.json"
    return PurePosixPath(*target_parts).as_posix()


def _insert_dict_row(conn: sqlite3.Connection, table: str, row: dict[str, Any], overrides: dict[str, Any] | None = None, *, skip: set[str] | None = None) -> None:
    """Insert one row using the destination schema's existing columns."""
    overrides = dict(overrides or {})
    skip = set(skip or set())
    columns = {str(item[1]) for item in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    values = {key: value for key, value in row.items() if key in columns and key not in skip}
    values.update({key: value for key, value in overrides.items() if key in columns and key not in skip})
    names = list(values)
    placeholders = ",".join("?" for _ in names)
    conn.execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({placeholders})", tuple(values[name] for name in names))


def _source_default_branch(conn: sqlite3.Connection, story_id: str) -> str | None:
    stable_id = default_branch_id(story_id)
    row = conn.execute(
        "SELECT branch_id FROM story_branches WHERE branch_id = ? AND story_id = ? LIMIT 1",
        (stable_id, story_id),
    ).fetchone()
    if row:
        return str(row[0])
    # A pre-021 database may have a root branch without the deterministic
    # identifier. Preserve that legacy data while avoiding display-name based
    # identity once the stable main branch exists.
    row = conn.execute(
        "SELECT branch_id FROM story_branches WHERE story_id = ? AND parent_branch_id IS NULL ORDER BY created_at, branch_id LIMIT 1",
        (story_id,),
    ).fetchone()
    return str(row[0]) if row else None


def _prepare_story_copy_maps(conn: sqlite3.Connection, source_story_id: str, target_story_id: str) -> dict[str, dict[str, str]]:
    source_main = _source_default_branch(conn, source_story_id)
    target_main = default_branch_id(target_story_id)
    conn.execute(
        """
        INSERT OR IGNORE INTO story_branches
            (branch_id, story_id, name, description, source_worldline_id)
        VALUES (?, ?, '主线', '故事副本主线', 'main')
        """,
        (target_main, target_story_id),
    )
    branch_map: dict[str, str] = {}
    if source_main:
        branch_map[source_main] = target_main
    branch_rows = conn.execute(
        "SELECT * FROM story_branches WHERE story_id = ? ORDER BY CASE WHEN parent_branch_id IS NULL THEN 0 ELSE 1 END, created_at, branch_id",
        (source_story_id,),
    ).fetchall()
    for row in branch_rows:
        source_id = str(row["branch_id"])
        if source_id in branch_map:
            continue
        branch_map[source_id] = _copy_scoped_id("branch", target_story_id, source_id)
    checkpoint_map = {
        str(row["checkpoint_id"]): _copy_scoped_id("checkpoint", target_story_id, str(row["checkpoint_id"]))
        for row in conn.execute(
            "SELECT checkpoint_id FROM branch_checkpoints WHERE branch_id IN (SELECT branch_id FROM story_branches WHERE story_id = ?)",
            (source_story_id,),
        ).fetchall()
    }
    session_map = {
        str(row["session_id"]): _copy_scoped_id("session", target_story_id, str(row["session_id"]))
        for row in conn.execute("SELECT session_id FROM creative_sessions WHERE story_id = ?", (source_story_id,)).fetchall()
    }
    turn_map = {
        str(row["turn_id"]): _copy_scoped_id("turn", target_story_id, str(row["turn_id"]))
        for row in conn.execute(
            "SELECT turn.turn_id FROM creative_turns AS turn JOIN creative_sessions AS session ON session.session_id = turn.session_id WHERE session.story_id = ?",
            (source_story_id,),
        ).fetchall()
    }
    fragment_map = {
        str(row["fragment_id"]): _copy_scoped_id("fragment", target_story_id, str(row["fragment_id"]))
        for row in conn.execute(
            "SELECT fragment.fragment_id FROM creative_fragments AS fragment JOIN creative_sessions AS session ON session.session_id = fragment.session_id WHERE session.story_id = ?",
            (source_story_id,),
        ).fetchall()
    }
    knowledge_map = {
        str(row["knowledge_id"]): _copy_scoped_id("knowledge", target_story_id, str(row["knowledge_id"]))
        for row in conn.execute("SELECT knowledge_id FROM knowledge_items WHERE story_id = ?", (source_story_id,)).fetchall()
    }
    entity_map: dict[str, str] = {}
    for row in conn.execute("SELECT entity_id, entity_type, canonical_name, worldline_id, version_scope, branch_id FROM entities WHERE story_id = ?", (source_story_id,)).fetchall():
        source_branch = str(row["branch_id"] or source_main or "")
        target_branch = branch_map.get(source_branch, target_main)
        entity_map[str(row["entity_id"])] = entity_id_for(
            str(row["entity_type"]), str(row["canonical_name"]),
            ("story", target_story_id, target_branch, str(row["worldline_id"] or ""), str(row["version_scope"] or "project_main")),
        )
    alias_map = {
        str(row["alias_group_id"]): _copy_scoped_id("alias", target_story_id, str(row["alias_group_id"]))
        for row in conn.execute("SELECT alias_group_id FROM entity_alias_groups WHERE story_id = ?", (source_story_id,)).fetchall()
    }
    revision_map = {
        str(row["revision_id"]): _copy_scoped_id("knowledge_revision", target_story_id, str(row["revision_id"]))
        for row in conn.execute(
            "SELECT revision_id FROM knowledge_revisions WHERE knowledge_id IN (SELECT knowledge_id FROM knowledge_items WHERE story_id = ?)",
            (source_story_id,),
        ).fetchall()
    }
    evidence_map = {
        str(row["evidence_id"]): _copy_scoped_id("evidence", target_story_id, str(row["evidence_id"]))
        for row in conn.execute(
            "SELECT evidence_id FROM knowledge_evidence WHERE knowledge_id IN (SELECT knowledge_id FROM knowledge_items WHERE story_id = ?)",
            (source_story_id,),
        ).fetchall()
    }
    edge_map = {
        str(row["edge_id"]): _copy_scoped_id("edge", target_story_id, str(row["edge_id"]))
        for row in conn.execute("SELECT edge_id FROM graph_edges WHERE story_id = ?", (source_story_id,)).fetchall()
    }
    binding_map = {
        str(row["binding_id"]): _copy_scoped_id("binding", target_story_id, str(row["binding_id"]))
        for row in conn.execute("SELECT binding_id FROM story_library_bindings WHERE story_id = ?", (source_story_id,)).fetchall()
    }
    return {
        "branch": branch_map,
        "checkpoint": checkpoint_map,
        "session": session_map,
        "turn": turn_map,
        "fragment": fragment_map,
        "knowledge": knowledge_map,
        "entity": entity_map,
        "alias": alias_map,
        "revision": revision_map,
        "evidence": evidence_map,
        "edge": edge_map,
        "binding": binding_map,
        "source_main": {"id": source_main or ""},
        "target_main": {"id": target_main},
    }


def _copy_story_branch_rows(conn: sqlite3.Connection, source_story_id: str, target_story_id: str, maps: dict[str, dict[str, str]]) -> None:
    branch_map = maps["branch"]
    for row in conn.execute("SELECT * FROM story_branches WHERE story_id = ? ORDER BY CASE WHEN parent_branch_id IS NULL THEN 0 ELSE 1 END, created_at, branch_id", (source_story_id,)).fetchall():
        source_id = str(row["branch_id"])
        target_id = branch_map[source_id]
        if target_id == maps["target_main"]["id"]:
            continue
        _insert_dict_row(conn, "story_branches", dict(row), {
            "branch_id": target_id, "story_id": target_story_id,
            "parent_branch_id": branch_map.get(str(row["parent_branch_id"] or "")) or None,
            "fork_fragment_id": maps["fragment"].get(str(row["fork_fragment_id"] or "")) or None,
            "fork_checkpoint_id": maps["checkpoint"].get(str(row["fork_checkpoint_id"] or "")) or None,
            "head_checkpoint_id": maps["checkpoint"].get(str(row["head_checkpoint_id"] or "")) or None,
            "status": str(row["status"] or "active"),
        }, skip={"created_at", "updated_at", "archived_at"})


def _copy_story_entity_rows(conn: sqlite3.Connection, source_story_id: str, target_story_id: str, maps: dict[str, dict[str, str]]) -> None:
    for row in conn.execute("SELECT * FROM entity_alias_groups WHERE story_id = ?", (source_story_id,)).fetchall():
        data = dict(row)
        _insert_dict_row(conn, "entity_alias_groups", data, {
            "alias_group_id": maps["alias"].get(str(row["alias_group_id"]), str(row["alias_group_id"])),
            "story_id": target_story_id,
            "metadata_json": _rewrite_json_text(row["metadata_json"], source_story_id=source_story_id, target_story_id=target_story_id, run_id_map={}, asset_id_map={}, branch_id_map=maps["branch"], knowledge_id_map=maps["knowledge"], entity_id_map=maps["entity"]),
            "deleted_at": None,
        }, skip={"created_at", "updated_at"})
    for row in conn.execute("SELECT * FROM entities WHERE story_id = ?", (source_story_id,)).fetchall():
        source_branch = str(row["branch_id"] or maps["source_main"]["id"] or "")
        _insert_dict_row(conn, "entities", dict(row), {
            "entity_id": maps["entity"].get(str(row["entity_id"]), str(row["entity_id"])),
            "story_id": target_story_id,
            "branch_id": maps["branch"].get(source_branch, maps["target_main"]["id"]),
            "alias_group_id": maps["alias"].get(str(row["alias_group_id"] or "")) or None,
            "deleted_at": None,
        }, skip={"created_at", "updated_at"})


def _copy_story_knowledge_rows(conn: sqlite3.Connection, source_story_id: str, target_story_id: str, maps: dict[str, dict[str, str]]) -> None:
    rewrite = dict(source_story_id=source_story_id, target_story_id=target_story_id, run_id_map={}, asset_id_map={}, branch_id_map=maps["branch"], knowledge_id_map=maps["knowledge"], entity_id_map=maps["entity"], binding_id_map=maps["binding"], checkpoint_id_map=maps["checkpoint"])

    def _knowledge_payload(raw: Any, target_id: str) -> str:
        rewritten = _rewrite_json_text(raw, **rewrite)
        try:
            payload = json.loads(rewritten)
        except (TypeError, ValueError):
            return rewritten
        if isinstance(payload, dict):
            # Category readers use the editable payload's id when sending an
            # update back through the knowledge service. A story copy must
            # expose its new physical identity there too.
            payload["id"] = target_id
            payload["knowledge_id"] = target_id
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    rows = conn.execute("SELECT * FROM knowledge_items WHERE story_id = ?", (source_story_id,)).fetchall()
    for row in rows:
        data = dict(row)
        source_branch = str(row["branch_id"] or maps["source_main"]["id"] or "")
        overrides = {
            "knowledge_id": maps["knowledge"].get(str(row["knowledge_id"]), str(row["knowledge_id"])),
            "story_id": target_story_id,
            "branch_id": maps["branch"].get(source_branch, maps["target_main"]["id"]),
            "entity_id": maps["entity"].get(str(row["entity_id"] or "")) or None,
            "superseded_by": maps["knowledge"].get(str(row["superseded_by"] or "")) or None,
            "content_json": _knowledge_payload(row["content_json"], maps["knowledge"].get(str(row["knowledge_id"]), str(row["knowledge_id"]))),
            "structured_json": _rewrite_json_text(row["structured_json"], **rewrite),
            "deleted_at": None,
        }
        _insert_dict_row(conn, "knowledge_items", data, overrides, skip={"created_at", "updated_at"})
    for row in conn.execute("SELECT * FROM knowledge_revisions WHERE knowledge_id IN (SELECT knowledge_id FROM knowledge_items WHERE story_id = ?)", (source_story_id,)).fetchall():
        _insert_dict_row(conn, "knowledge_revisions", dict(row), {
            "revision_id": maps["revision"].get(str(row["revision_id"]), str(row["revision_id"])),
            "knowledge_id": maps["knowledge"].get(str(row["knowledge_id"]), str(row["knowledge_id"])),
            "snapshot_json": _rewrite_json_text(row["snapshot_json"], **rewrite),
        }, skip={"created_at"})
    for row in conn.execute("SELECT * FROM knowledge_evidence WHERE knowledge_id IN (SELECT knowledge_id FROM knowledge_items WHERE story_id = ?)", (source_story_id,)).fetchall():
        _insert_dict_row(conn, "knowledge_evidence", dict(row), {
            "evidence_id": maps["evidence"].get(str(row["evidence_id"]), str(row["evidence_id"])),
            "knowledge_id": maps["knowledge"].get(str(row["knowledge_id"]), str(row["knowledge_id"])),
            "location_json": _rewrite_json_text(row["location_json"], **rewrite),
        }, skip={"created_at"})
    for row in conn.execute("SELECT * FROM graph_edges WHERE story_id = ?", (source_story_id,)).fetchall():
        _insert_dict_row(conn, "graph_edges", dict(row), {
            "edge_id": maps["edge"].get(str(row["edge_id"]), str(row["edge_id"])),
            "story_id": target_story_id,
            "source_node_id": maps["entity"].get(str(row["source_node_id"]), str(row["source_node_id"])),
            "target_node_id": maps["entity"].get(str(row["target_node_id"]), str(row["target_node_id"])),
            "evidence_id": maps["evidence"].get(str(row["evidence_id"] or "")) or None,
            "metadata_json": _rewrite_json_text(row["metadata_json"], **rewrite),
            "deleted_at": None,
        }, skip={"created_at", "updated_at"})


def _copy_story_checkpoint_rows(conn: sqlite3.Connection, source_story_id: str, target_story_id: str, maps: dict[str, dict[str, str]]) -> None:
    rewrite = dict(source_story_id=source_story_id, target_story_id=target_story_id, run_id_map={}, asset_id_map={}, branch_id_map=maps["branch"], session_id_map=maps["session"], turn_id_map=maps["turn"], fragment_id_map=maps["fragment"], knowledge_id_map=maps["knowledge"], binding_id_map=maps["binding"], checkpoint_id_map=maps["checkpoint"], entity_id_map=maps["entity"])
    source_branch_ids = tuple(maps["branch"])
    if not source_branch_ids:
        return
    placeholders = ",".join("?" for _ in source_branch_ids)
    checkpoints = conn.execute(
        f"SELECT * FROM branch_checkpoints WHERE branch_id IN ({placeholders}) ORDER BY branch_id, revision, checkpoint_id",
        source_branch_ids,
    ).fetchall()
    pending_parents: list[tuple[str, str | None]] = []
    for row in checkpoints:
        target_checkpoint_id = maps["checkpoint"].get(str(row["checkpoint_id"]), str(row["checkpoint_id"]))
        source_parent_id = str(row["parent_checkpoint_id"] or "")
        target_parent_id = maps["checkpoint"].get(source_parent_id) or None
        rewritten_manifest = _rewrite_json_text(row["snapshot_manifest_json"], **rewrite)
        try:
            manifest_object = json.loads(rewritten_manifest)
            canonical_manifest = json.dumps(
                manifest_object, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        except (TypeError, ValueError):
            canonical_manifest = rewritten_manifest
        manifest_hash = hashlib.sha256(canonical_manifest.encode("utf-8")).hexdigest()
        _insert_dict_row(conn, "branch_checkpoints", dict(row), {
            "checkpoint_id": target_checkpoint_id,
            "branch_id": maps["branch"].get(str(row["branch_id"]), maps["target_main"]["id"]),
            # Insert parents after every checkpoint exists. A source branch
            # may have checkpoints created in the same timestamp/revision
            # order, so SQL ordering is not a safe dependency guarantee.
            "parent_checkpoint_id": None,
            "frontier_fragment_id": maps["fragment"].get(str(row["frontier_fragment_id"] or "")) or None,
            "snapshot_manifest_json": canonical_manifest,
            "snapshot_hash": manifest_hash,
        })
        pending_parents.append((target_checkpoint_id, target_parent_id))
    for target_checkpoint_id, target_parent_id in pending_parents:
        if target_parent_id:
            conn.execute(
                "UPDATE branch_checkpoints SET parent_checkpoint_id = ? WHERE checkpoint_id = ?",
                (target_parent_id, target_checkpoint_id),
            )
    for row in conn.execute(
        f"SELECT item.* FROM branch_checkpoint_items AS item JOIN branch_checkpoints AS checkpoint ON checkpoint.checkpoint_id = item.checkpoint_id WHERE checkpoint.branch_id IN ({placeholders}) ORDER BY item.checkpoint_id, item.item_kind, item.ordinal, item.item_id",
        source_branch_ids,
    ).fetchall():
        item_id = str(row["item_id"])
        kind = str(row["item_kind"])
        mapped_item = maps["knowledge"].get(item_id) if kind == "knowledge" else maps["fragment"].get(item_id) if kind == "fragment" else item_id
        _insert_dict_row(conn, "branch_checkpoint_items", dict(row), {
            "checkpoint_id": maps["checkpoint"].get(str(row["checkpoint_id"]), str(row["checkpoint_id"])),
            "item_id": mapped_item or item_id,
            "item_revision_id": maps["revision"].get(str(row["item_revision_id"] or "")) or row["item_revision_id"],
            "origin_id": maps["knowledge"].get(str(row["origin_id"] or "")) or row["origin_id"],
            "payload_json": _rewrite_json_text(row["payload_json"], **rewrite),
        })
    for row in conn.execute(
        f"SELECT state.* FROM branch_fragment_states AS state WHERE state.branch_id IN ({placeholders}) ORDER BY state.branch_id, state.ordinal, state.fragment_id",
        source_branch_ids,
    ).fetchall():
        _insert_dict_row(conn, "branch_fragment_states", dict(row), {
            "branch_id": maps["branch"].get(str(row["branch_id"]), maps["target_main"]["id"]),
            "fragment_id": maps["fragment"].get(str(row["fragment_id"]), str(row["fragment_id"])),
            "checkpoint_id": maps["checkpoint"].get(str(row["checkpoint_id"] or "")) or None,
            "source_branch_id": maps["branch"].get(str(row["source_branch_id"] or "")) or None,
        })


def _copy_story_library_bindings(conn: sqlite3.Connection, source_story_id: str, target_story_id: str, maps: dict[str, dict[str, str]]) -> None:
    for row in conn.execute(
        "SELECT * FROM story_library_bindings WHERE story_id = ? ORDER BY created_at, binding_id",
        (source_story_id,),
    ).fetchall():
        source_branch = str(row["branch_id"] or maps["source_main"]["id"] or "")
        target_binding_id = maps["binding"].get(str(row["binding_id"]), _copy_scoped_id("binding", target_story_id, str(row["binding_id"])))
        _insert_dict_row(conn, "story_library_bindings", dict(row), {
            "binding_id": target_binding_id,
            "story_id": target_story_id,
            "branch_id": maps["branch"].get(source_branch, maps["target_main"]["id"]),
            "idempotency_key": f"story-copy:{target_story_id}:{row['binding_id']}",
            "status": str(row["status"] or "ready"),
            "removed_at": row["removed_at"] if str(row["status"] or "") == "archived" else None,
        }, skip={"created_at", "updated_at"})
        for link in conn.execute("SELECT * FROM story_library_item_links WHERE binding_id = ?", (row["binding_id"],)).fetchall():
            _insert_dict_row(conn, "story_library_item_links", dict(link), {
                "binding_id": target_binding_id,
                "local_knowledge_id": maps["knowledge"].get(str(link["local_knowledge_id"] or "")) or link["local_knowledge_id"],
                "local_entity_id": maps["entity"].get(str(link["local_entity_id"] or "")) or link["local_entity_id"],
            })
        for link in conn.execute("SELECT * FROM story_library_entity_links WHERE binding_id = ?", (row["binding_id"],)).fetchall():
            _insert_dict_row(conn, "story_library_entity_links", dict(link), {
                "binding_id": target_binding_id,
                "local_entity_id": maps["entity"].get(str(link["local_entity_id"] or "")) or link["local_entity_id"],
            })


def clone_story_storage_rows(
    conn: sqlite3.Connection,
    source_story_id: str,
    target_story_id: str,
    *,
    include_discussions: bool = True,
    include_summaries: bool = True,
    include_chapters: bool = True,
) -> dict:
    """Clone DB-only story assets and workflow history into a new story.

    The caller owns the surrounding transaction. IDs that are global primary
    keys are remapped so a copy never moves or overwrites records belonging to
    the source story.
    """

    source_story_id = str(source_story_id or "").strip()
    target_story_id = str(target_story_id or "").strip()
    if not source_story_id or not target_story_id:
        raise ValueError("Source and target story IDs are required.")
    if source_story_id == target_story_id:
        raise ValueError("Source and target story IDs must differ.")
    if not _active_story_exists(conn, source_story_id):
        raise ValueError(f"Source story does not exist: {source_story_id}")
    if not _active_story_exists(conn, target_story_id):
        raise ValueError(f"Target story does not exist: {target_story_id}")

    # Build every identity map before copying payloads. This is the boundary
    # that keeps the new story's branches, sessions, knowledge, entities and
    # library bindings from retaining references to the source story.
    copy_maps = _prepare_story_copy_maps(conn, source_story_id, target_story_id)
    _copy_story_branch_rows(conn, source_story_id, target_story_id, copy_maps)
    _copy_story_entity_rows(conn, source_story_id, target_story_id, copy_maps)
    _copy_story_knowledge_rows(conn, source_story_id, target_story_id, copy_maps)
    _copy_story_library_bindings(conn, source_story_id, target_story_id, copy_maps)
    _copy_story_checkpoint_rows(conn, source_story_id, target_story_id, copy_maps)

    workflow_rows = []
    run_id_map: dict[str, str] = {}
    if include_chapters:
        workflow_rows = conn.execute(
            """
            SELECT run_id, workflow_type, status, parent_run_id, input_json,
                   output_json, error_json, started_at, finished_at
            FROM workflow_runs
            WHERE story_id = ?
            ORDER BY created_at, run_id
            """,
            (source_story_id,),
        ).fetchall()
        for row in workflow_rows:
            source_run_id = str(row["run_id"])
            run_id_map[source_run_id] = _copy_run_id(conn, source_run_id, target_story_id)

    asset_rows = conn.execute(
        """
        SELECT asset.asset_id, asset.asset_type, asset.logical_key, asset.title,
               asset.relative_path, asset.content_hash, asset.mime_type,
               asset.source_kind, asset.source_ref, asset.metadata_json,
               payload.payload_json
        FROM asset_files AS asset
        LEFT JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE asset.story_id = ? AND asset.deleted_at IS NULL
        ORDER BY asset.created_at, asset.asset_id
        """,
        (source_story_id,),
    ).fetchall()

    included_assets = [
        row
        for row in asset_rows
        if _asset_is_included(
            str(row["asset_type"]),
            include_discussions=include_discussions,
            include_summaries=include_summaries,
            include_chapters=include_chapters,
        )
    ]
    asset_id_map: dict[str, str] = {}
    for row in included_assets:
        source_asset_id = str(row["asset_id"])
        asset_type = str(row["asset_type"])
        source_logical_key = str(row["logical_key"])
        target_logical_key = (
            run_id_map.get(source_logical_key, source_logical_key)
            if asset_type == "workflow_run_snapshot"
            else source_logical_key
        )
        seed = f"{target_story_id}:{asset_type}:{target_logical_key}"
        asset_id_map[source_asset_id] = "asset_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

    for row in included_assets:
        source_asset_id = str(row["asset_id"])
        target_asset_id = asset_id_map[source_asset_id]
        asset_type = str(row["asset_type"])
        source_logical_key = str(row["logical_key"])
        target_logical_key = (
            run_id_map.get(source_logical_key, source_logical_key)
            if asset_type == "workflow_run_snapshot"
            else source_logical_key
        )
        target_relative_path = _target_relative_path(
            str(row["relative_path"]),
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            source_run_id=source_logical_key if asset_type == "workflow_run_snapshot" else "",
            target_run_id=target_logical_key if asset_type == "workflow_run_snapshot" else "",
            branch_id_map=copy_maps["branch"],
        )
        rewrite_maps = {
            "branch_id_map": copy_maps["branch"],
            "session_id_map": copy_maps["session"],
            "turn_id_map": copy_maps["turn"],
            "fragment_id_map": copy_maps["fragment"],
            "knowledge_id_map": copy_maps["knowledge"],
            "binding_id_map": copy_maps["binding"],
            "checkpoint_id_map": copy_maps["checkpoint"],
            "entity_id_map": copy_maps["entity"],
        }
        metadata_json = _rewrite_json_text(
            row["metadata_json"],
            source_story_id=source_story_id,
            target_story_id=target_story_id,
            run_id_map=run_id_map,
            asset_id_map=asset_id_map,
            **rewrite_maps,
        )
        conn.execute(
            """
            INSERT INTO asset_files (
                asset_id, story_id, asset_type, logical_key, title, relative_path,
                content_hash, mime_type, source_kind, source_ref, metadata_json,
                created_at, updated_at, deleted_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now'), NULL
            )
            """,
            (
                target_asset_id,
                target_story_id,
                asset_type,
                target_logical_key,
                str(row["title"] or ""),
                target_relative_path,
                row["content_hash"],
                row["mime_type"],
                row["source_kind"],
                row["source_ref"],
                metadata_json,
            ),
        )
        if row["payload_json"] is not None:
            if asset_type == "generation_context_snapshot":
                # A context snapshot is an immutable record of the source
                # generation. Rewriting embedded story IDs would make its
                # persisted fingerprint inconsistent with the saved payload.
                payload_json = str(row["payload_json"])
            else:
                payload_json = _rewrite_json_text(
                    row["payload_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                    **rewrite_maps,
                )
            conn.execute(
                """
                INSERT INTO asset_payloads (asset_id, payload_json, created_at, updated_at)
                VALUES (
                    ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
                    strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
                )
                """,
                (target_asset_id, payload_json),
            )

    for row in workflow_rows:
        source_run_id = str(row["run_id"])
        target_run_id = run_id_map[source_run_id]
        parent_run_id = str(row["parent_run_id"] or "")
        conn.execute(
            """
            INSERT INTO workflow_runs (
                run_id, story_id, workflow_type, status, parent_run_id,
                input_json, output_json, error_json, started_at, finished_at, created_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            )
            """,
            (
                target_run_id,
                target_story_id,
                str(row["workflow_type"] or "chapter_pipeline"),
                str(row["status"] or "unknown"),
                run_id_map.get(parent_run_id) if parent_run_id else None,
                _rewrite_json_text(
                    row["input_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                    **rewrite_maps,
                ),
                _rewrite_json_text(
                    row["output_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                    **rewrite_maps,
                ),
                _rewrite_json_text(
                    row["error_json"],
                    source_story_id=source_story_id,
                    target_story_id=target_story_id,
                    run_id_map=run_id_map,
                    asset_id_map=asset_id_map,
                    **rewrite_maps,
                ),
                row["started_at"],
                row["finished_at"],
            ),
        )
        steps = conn.execute(
            """
            SELECT step_name, step_order, status, input_json, output_json,
                   error_json, artifact_asset_id, started_at, finished_at
            FROM workflow_steps
            WHERE run_id = ?
            ORDER BY step_order, step_id
            """,
            (source_run_id,),
        ).fetchall()
        for step in steps:
            step_name = str(step["step_name"] or "")
            step_id = f"{target_run_id}:{step_name}"
            conn.execute(
                """
                INSERT INTO workflow_steps (
                    step_id, run_id, step_name, step_order, status, input_json,
                    output_json, error_json, artifact_asset_id, started_at, finished_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step_id,
                    target_run_id,
                    step_name,
                    int(step["step_order"] or 0),
                    str(step["status"] or "unknown"),
                    _rewrite_json_text(
                        step["input_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                        **rewrite_maps,
                    ),
                    _rewrite_json_text(
                        step["output_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                        **rewrite_maps,
                    ),
                    _rewrite_json_text(
                        step["error_json"],
                        source_story_id=source_story_id,
                        target_story_id=target_story_id,
                        run_id_map=run_id_map,
                        asset_id_map=asset_id_map,
                        **rewrite_maps,
                    ),
                    asset_id_map.get(str(step["artifact_asset_id"] or "")),
                    step["started_at"],
                    step["finished_at"],
                ),
            )

    creative_session_result = (
        clone_creative_session_rows(
            conn,
            source_story_id,
            target_story_id,
            branch_id_map=copy_maps["branch"],
            asset_id_map=asset_id_map,
        )
        if include_chapters
        else {
            "session_count": 0,
            "turn_count": 0,
            "fragment_count": 0,
            "session_id_map": {},
        }
    )

    return {
        "asset_count": len(included_assets),
        "workflow_count": len(workflow_rows),
        "run_id_map": run_id_map,
        "branch_id_map": copy_maps["branch"],
        "knowledge_id_map": copy_maps["knowledge"],
        "binding_id_map": copy_maps["binding"],
        "creative_sessions": creative_session_result,
    }
