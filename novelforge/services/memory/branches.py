"""Story branch and checkpoint service facade.

The service owns project database transactions while ``storage.repositories``
contains the SQL and row mapping. Callers never derive a branch from the
current UI selection; every operation receives the explicit branch ID.
"""

from __future__ import annotations

import hashlib
import json

from novelforge.services import memory as _memory_api
from storage.db import transaction
from storage.repositories.branches import (
    archive_branch_row,
    create_branch_row,
    create_checkpoint_row,
    default_branch_id,
    ensure_default_branch,
    fork_branch_rows,
    list_branch_rows,
    list_checkpoint_rows,
    load_checkpoint_row,
    load_branch_for_story,
    load_branch_row,
    resolve_branch_context_row,
    update_branch_row,
    clone_checkpoint_fragments_to_session,
)
from storage.repositories.creative_sessions import create_creative_session_row
from storage.repositories.assets import register_asset_file, upsert_asset_payload
from storage.repositories.story_reference_libraries import load_story_reference_state as _load_story_reference_state
from uuid import uuid4


BRANCH_CONFIGURATION_ASSET_TYPE = "branch_configuration"


def _branch_configuration_key(branch_id: str) -> str:
    return f"branch:{str(branch_id or '').strip()}:configuration"


def _merge_branch_configuration(base: dict, override: dict | None) -> dict:
    """Apply mutable current-line configuration without rewriting checkpoints."""
    merged = {key: value for key, value in (base or {}).items()}
    if not isinstance(override, dict):
        return merged
    for key in ("profile", "story_rules", "story_prompt_options", "context_directives"):
        if key in override:
            value = override.get(key)
            merged[key] = dict(value) if key in {"profile", "story_rules"} and isinstance(value, dict) else value
    if isinstance(override.get("rule_conflict_resolutions"), dict):
        conflicts = dict(merged.get("rule_conflict_resolutions") or {})
        if "story" in override["rule_conflict_resolutions"]:
            conflicts["story"] = list(override["rule_conflict_resolutions"].get("story") or [])
        merged["rule_conflict_resolutions"] = conflicts
    return merged


def load_story_branch_configuration(project_name: str, story_id: str, branch_id: str) -> dict:
    """Return the current branch configuration overlay, if one was edited."""
    payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type=BRANCH_CONFIGURATION_ASSET_TYPE,
        logical_key=_branch_configuration_key(branch_id),
        story_id=story_id,
    )
    return dict(payload) if isinstance(payload, dict) else {}


def _load_branch_configuration_conn(conn, story_id: str, branch_id: str) -> dict:
    row = conn.execute(
        """
        SELECT payload.payload_json
        FROM asset_files AS asset
        JOIN asset_payloads AS payload ON payload.asset_id = asset.asset_id
        WHERE asset.story_id = ? AND asset.asset_type = ? AND asset.logical_key = ?
          AND asset.deleted_at IS NULL
        """,
        (story_id, BRANCH_CONFIGURATION_ASSET_TYPE, _branch_configuration_key(branch_id)),
    ).fetchone()
    if row is None:
        return {}
    try:
        payload = json.loads(row[0] or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def load_effective_story_branch_configuration(project_name: str, story_id: str, branch_id: str) -> dict:
    """Load frozen story configuration plus the current branch overlay."""
    load_story_branch(project_name, story_id, branch_id)
    return _load_configuration_snapshot(project_name, story_id, branch_id)


def save_story_branch_configuration(
    project_name: str,
    story_id: str,
    branch_id: str,
    override: dict,
) -> dict:
    """Persist a branch-owned configuration overlay.

    Story-level configuration remains the fallback. Only story-scoped values
    are accepted here, so a branch cannot mutate project/global settings.
    """
    if not isinstance(override, dict):
        raise ValueError("分支配置必须是对象。")
    clean: dict = {}
    for key in ("profile", "story_rules", "story_prompt_options", "context_directives"):
        if key in override:
            value = override[key]
            if key == "profile":
                value = _memory_api.CreativeProfile.model_validate(value or {}).model_dump()
            elif key == "story_rules":
                value = _memory_api.normalize_rules(value or {})
            elif key in {"story_prompt_options", "context_directives"}:
                value = list(value or []) if isinstance(value, list) else []
            clean[key] = value
    conflicts = override.get("rule_conflict_resolutions")
    if isinstance(conflicts, dict) and "story" in conflicts:
        clean["rule_conflict_resolutions"] = {"story": list(conflicts.get("story") or [])}
    path = _memory_api._story_path_from_project_path(
        project_name, story_id, "branch_configurations", "configuration.json"
    ).resolve()
    project_root = _memory_api.project_path(project_name).resolve()
    relative_path = str(path.relative_to(project_root)).replace("\\", "/")
    logical_key = _branch_configuration_key(branch_id)
    asset_id = "asset_" + hashlib.sha256(
        f"{story_id}:{BRANCH_CONFIGURATION_ASSET_TYPE}:{logical_key}".encode("utf-8")
    ).hexdigest()[:24]
    with _db(project_name) as conn:
        # Configuration edits must serialize with archive/fork/checkpoint
        # operations. A deferred transaction would let two writers read the
        # same overlay and lose one field during the merge.
        conn.execute("BEGIN IMMEDIATE")
        try:
            branch = load_branch_for_story(conn, story_id, branch_id)
            if str(branch.get("status") or "active") != "active":
                raise ValueError("已归档的世界线不能修改配置。")
            current = _load_branch_configuration_conn(conn, story_id, branch_id)
            current.update(clean)
            register_asset_file(
                conn,
                asset_id=asset_id,
                story_id=story_id,
                asset_type=BRANCH_CONFIGURATION_ASSET_TYPE,
                logical_key=logical_key,
                title=f"{branch.get('name') or '世界线'}配置",
                relative_path=relative_path,
                mime_type="application/json",
                source_kind="branch_configuration",
                metadata={"branch_id": branch_id, "story_id": story_id},
            )
            if not upsert_asset_payload(
                conn,
                asset_type=BRANCH_CONFIGURATION_ASSET_TYPE,
                logical_key=logical_key,
                story_id=story_id,
                payload=current,
            ):
                raise RuntimeError("分支配置未能写入项目数据库。")
            conn.commit()
            return current
        except Exception:
            conn.rollback()
            raise


def _db(project_name: str):
    return _memory_api.open_project_db(_memory_api.project_path(project_name).resolve())


def _load_configuration_snapshot(project_name: str, story_id: str, branch_id: str | None = None) -> dict:
    snapshot = {
        "profile": _memory_api.load_creative_profile(project_name, story_id) or {},
        "global_rules": _memory_api.load_global_rules() or {},
        "project_rules": _memory_api.load_project_rules(project_name) or {},
        "global_prompt_options": _memory_api.load_global_prompt_options() or [],
        "project_prompt_options": _memory_api.load_project_prompt_options(project_name) or [],
        "story_prompt_options": _memory_api.load_story_prompt_options(project_name, story_id) or [],
        "context_directives": _memory_api.load_context_directives(project_name, story_id) or [],
        "story_rules": _memory_api.load_story_rules(project_name, story_id) or {},
        "rule_conflict_resolutions": {
            "global": _memory_api.load_rule_conflict_resolutions(project_name, "global", story_id) or [],
            "project": _memory_api.load_rule_conflict_resolutions(project_name, "project", story_id) or [],
            "story": _memory_api.load_rule_conflict_resolutions(project_name, "story", story_id) or [],
        },
    }
    if branch_id and str(branch_id) != default_branch_id(story_id):
        # 旁支创建后，父线 story 级配置的后续编辑不能回灌当前旁支。
        # 有 head checkpoint 时以其冻结配置为基线；首个检查点才使用
        # 当前故事配置，再叠加该线自己的可变 overlay。
        with _db(project_name) as conn:
            branch = load_branch_for_story(conn, story_id, branch_id)
            head_id = str(branch.get("head_checkpoint_id") or "")
            if head_id:
                checkpoint = load_checkpoint_row(conn, head_id) or {}
                manifest = checkpoint.get("snapshot_manifest") or {}
                frozen = manifest.get("configuration")
                if isinstance(frozen, dict) and frozen:
                    snapshot = dict(frozen)
                if isinstance(manifest.get("story_rules"), dict):
                    snapshot["story_rules"] = dict(manifest.get("story_rules") or {})
        return _merge_branch_configuration(
            snapshot, load_story_branch_configuration(project_name, story_id, branch_id)
        )
    return snapshot


def ensure_story_branch(project_name: str, story_id: str, branch_id: str | None = None) -> dict:
    with _db(project_name) as conn:
        with transaction(conn):
            ensure_default_branch(conn, story_id)
            selected = branch_id or default_branch_id(story_id)
            return load_branch_for_story(conn, story_id, selected)


def story_reference_mode(project_name: str, story_id: str) -> str:
    """Return the story reference gate used for main-branch compatibility."""
    with _db(project_name) as conn:
        return str(_load_story_reference_state(conn, story_id=story_id).get("read_mode") or "legacy").strip().lower()


def list_story_branches(project_name: str, story_id: str, *, include_archived: bool = False) -> list[dict]:
    with _db(project_name) as conn:
        with transaction(conn):
            ensure_default_branch(conn, story_id)
            return list_branch_rows(conn, story_id, include_archived=include_archived)


def load_story_branch(project_name: str, story_id: str, branch_id: str | None = None) -> dict:
    return ensure_story_branch(project_name, story_id, branch_id)


def create_story_branch(
    project_name: str,
    story_id: str,
    *,
    name: str,
    description: str = "",
    parent_branch_id: str | None = None,
    fork_fragment_id: str | None = None,
    fork_checkpoint_id: str | None = None,
    source_worldline_id: str = "main",
) -> dict:
    with _db(project_name) as conn:
        with transaction(conn):
            if _load_story_reference_state(conn, story_id=story_id).get("read_mode") != "strict":
                raise ValueError("请先确认旧故事的资料使用范围，再创建世界线。")
            ensure_default_branch(conn, story_id)
            parent = parent_branch_id or default_branch_id(story_id)
            return create_branch_row(
                conn,
                story_id=story_id,
                name=name,
                description=description,
                parent_branch_id=parent if (fork_fragment_id or fork_checkpoint_id) else None,
                fork_fragment_id=fork_fragment_id,
                fork_checkpoint_id=fork_checkpoint_id,
                source_worldline_id=source_worldline_id,
            )


def fork_story_branch(
    project_name: str,
    story_id: str,
    *,
    parent_branch_id: str,
    name: str,
    description: str = "",
    fork_fragment_id: str | None = None,
    fork_checkpoint_id: str | None = None,
    allow_current_state: bool = False,
    create_session: bool = True,
) -> dict:
    # Capture the parent's effective configuration before taking the write
    # transaction.  fork_branch_rows may materialize a new current-state
    # checkpoint, and that checkpoint must contain the same profile/rules/
    # prompts/directives overlay that the caller just selected.  Keeping this
    # read outside the transaction also avoids opening a second connection
    # while the branch rows are being written.
    configuration_snapshot = _load_configuration_snapshot(
        project_name, story_id, parent_branch_id
    )
    with _db(project_name) as conn:
        with transaction(conn):
            if _load_story_reference_state(conn, story_id=story_id).get("read_mode") != "strict":
                raise ValueError("请先确认旧故事的资料使用范围，再创建世界线。")
            ensure_default_branch(conn, story_id)
            branch = fork_branch_rows(
                conn,
                story_id=story_id,
                parent_branch_id=parent_branch_id,
                name=name,
                description=description,
                fork_fragment_id=fork_fragment_id,
                fork_checkpoint_id=fork_checkpoint_id,
                allow_current_state=allow_current_state,
                configuration_snapshot=configuration_snapshot,
            )
            result = {"branch": branch}
            if create_session:
                session_id = f"session_{uuid4().hex}"
                session = create_creative_session_row(conn, {
                    "session_id": session_id,
                    "story_id": story_id,
                    "title": f"{branch.get('name') or '世界线'} · 自由创作",
                    "session_goal": "从分叉点继续创作",
                    "branch_id": branch["branch_id"],
                    "worldline_id": branch.get("source_worldline_id") or "main",
                    "auto_extract_mode": "manual",
                })
                clone_result = clone_checkpoint_fragments_to_session(
                    conn,
                    checkpoint_id=branch.get("head_checkpoint_id") or "",
                    child_branch_id=branch["branch_id"],
                    session_id=session_id,
                )
                if clone_result.get("fragment_id"):
                    session = dict(session)
                    session["active_fragment_id"] = clone_result["fragment_id"]
                result["session"] = session
            return result


def archive_story_branch(project_name: str, story_id: str, branch_id: str) -> dict:
    with _db(project_name) as conn:
        with transaction(conn):
            return archive_branch_row(conn, story_id, branch_id)


def update_story_branch(project_name: str, story_id: str, branch_id: str, updates: dict) -> dict:
    with _db(project_name) as conn:
        with transaction(conn):
            return update_branch_row(conn, story_id, branch_id, updates)


def create_story_checkpoint(
    project_name: str,
    story_id: str,
    branch_id: str,
    *,
    frontier_fragment_id: str | None = None,
    extraction_status: str = "ready",
    reason: str = "",
    allow_current_state: bool = False,
) -> dict:
    # 配置也属于分支基线的一部分。只在创建检查点时读取一次，后续父线
    # 编辑 profile、导演注或提示选项不会回写已经物化的旁支历史。
    configuration_snapshot = _load_configuration_snapshot(project_name, story_id, branch_id)
    with _db(project_name) as conn:
        with transaction(conn):
            load_branch_for_story(conn, story_id, branch_id)
            return create_checkpoint_row(
                conn,
                branch_id=branch_id,
                frontier_fragment_id=frontier_fragment_id,
                extraction_status=extraction_status,
                reason=reason,
                allow_current_state=allow_current_state,
                configuration_snapshot=configuration_snapshot,
            )


def list_story_checkpoints(project_name: str, story_id: str, branch_id: str) -> list[dict]:
    with _db(project_name) as conn:
        with transaction(conn):
            load_branch_for_story(conn, story_id, branch_id)
            return list_checkpoint_rows(conn, branch_id)


def resolve_branch_context(project_name: str, story_id: str, branch_id: str | None = None) -> dict:
    selected = branch_id or default_branch_id(story_id)
    configuration_snapshot = _load_configuration_snapshot(project_name, story_id, selected)
    branch_override = load_story_branch_configuration(project_name, story_id, selected)
    with _db(project_name) as conn:
        with _memory_api.transaction(conn):
            ensure_default_branch(conn, story_id)
            context = resolve_branch_context_row(
                conn,
                story_id,
                selected,
                configuration_snapshot=configuration_snapshot,
            )
            # 默认主线承接现有 story 级编辑；旁支以自身 head checkpoint
            # 为冻结基线，只有 branch overlay 可以改变它。
            base_configuration = (
                configuration_snapshot
                if str(selected) == default_branch_id(story_id)
                else (context.get("configuration") or {})
            )
            context["configuration"] = _merge_branch_configuration(base_configuration, branch_override)
            if isinstance(context["configuration"].get("story_rules"), dict):
                context["story_rules"] = dict(context["configuration"]["story_rules"])
            return context
