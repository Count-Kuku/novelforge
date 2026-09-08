"""Implementation slice for the memory facade: rule conflict resolutions."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

from novelforge.domain.creation_modes import (
    DEFAULT_CREATION_MODE,
    normalize_creation_mode,
)

def normalize_rule_conflict_resolutions(items: list | None, source: str = "") -> list[dict]:
    normalized: list[dict] = []
    if not isinstance(items, list):
        return normalized
    for item in items:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision", "") or "").strip()
        if not decision:
            continue
        scope = str(item.get("scope", "all") or "all").strip()
        if scope not in _memory_api.RULE_SCOPES:
            scope = "all"
        title = str(item.get("title", "") or "").strip() or decision[:40]
        payload = {
            "id": str(item.get("id", "") or _memory_api.uuid4()).strip(),
            "scope": scope,
            "title": title,
            "decision": decision,
            "updated_at": str(item.get("updated_at", "") or _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds")),
        }
        if source:
            payload["source"] = source
        normalized.append(payload)
    return normalized


def _rule_conflict_resolution_path(project_name: str, layer: str, story_id: str = "default") -> _memory_api.Path:
    if layer == "global":
        return _memory_api.GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH
    if layer == "story":
        return _memory_api._story_rule_conflict_resolutions_path(project_name, story_id)
    return _memory_api._project_rule_conflict_resolutions_path(project_name)


def load_rule_conflict_resolutions(
    project_name: str,
    layer: str = "story",
    story_id: str = "default",
    branch_id: str | None = None,
) -> list[dict]:
    if branch_id and layer == "story" and str(branch_id) != _memory_api.default_branch_id(story_id):
        configuration = _memory_api.load_effective_story_branch_configuration(project_name, story_id, branch_id)
        return normalize_rule_conflict_resolutions(
            (configuration.get("rule_conflict_resolutions") or {}).get("story") or []
        )
    if layer == "global":
        db_items = _memory_api._load_global_from_db_best_effort(
            lambda conn: _memory_api.load_global_setting(conn, "rule_conflict_resolutions"),
            "global rule conflict resolutions",
        )
        if isinstance(db_items, list):
            return normalize_rule_conflict_resolutions(db_items)
    if layer != "global":
        logical_key = f"{layer}:{story_id if layer == 'story' else 'project'}"
        db_items = _memory_api._load_asset_payload_from_db_best_effort(
            project_name,
            asset_type="rule_conflict_resolutions",
            logical_key=logical_key,
            story_id=story_id if layer == "story" else None,
        )
        if isinstance(db_items, list):
            return normalize_rule_conflict_resolutions(db_items)
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    if not path.exists():
        return []
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    normalized = normalize_rule_conflict_resolutions(raw if isinstance(raw, list) else None)
    if layer == "global":
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", normalized)
        )
    return normalized


def save_rule_conflict_resolutions(
    project_name: str,
    layer: str,
    resolutions: list[dict],
    story_id: str = "default",
    branch_id: str | None = None,
) -> list[dict]:
    if branch_id and layer == "story" and str(branch_id) != _memory_api.default_branch_id(story_id):
        normalized = normalize_rule_conflict_resolutions(resolutions)
        _memory_api.save_story_branch_configuration(
            project_name,
            story_id,
            branch_id,
            {"rule_conflict_resolutions": {"story": normalized}},
        )
        return normalized
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    normalized = normalize_rule_conflict_resolutions(resolutions)
    logical_key = f"{layer}:{story_id if layer == 'story' else 'project'}"
    if not normalized:
        if path.exists():
            path.unlink()
        if layer == "global":
            _memory_api._sync_global_to_db_best_effort(
                lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", [])
            )
        if layer != "global":
            _memory_api.mark_asset_deleted_record(
                project_name,
                asset_type="rule_conflict_resolutions",
                logical_key=logical_key,
                story_id=story_id if layer == "story" else None,
            )
        return []
    if layer == "global":
        _memory_api._sync_global_to_db_best_effort(
            lambda conn: _memory_api.sync_global_setting(conn, "rule_conflict_resolutions", normalized)
        )
    if layer != "global":
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            path,
            asset_type="rule_conflict_resolutions",
            logical_key=logical_key,
            story_id=story_id if layer == "story" else None,
            title=f"{layer.title()} Rule Conflict Resolutions",
            payload=normalized,
        )
    return normalized


def add_rule_conflict_resolution(
    project_name: str,
    layer: str,
    scope: str,
    title: str,
    decision: str,
    story_id: str = "default",
    branch_id: str | None = None,
) -> dict:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id, branch_id)
    normalized_items = normalize_rule_conflict_resolutions([{
        "id": str(_memory_api.uuid4()),
        "scope": scope,
        "title": title,
        "decision": decision,
        "updated_at": _memory_api.datetime.now(_memory_api.timezone.utc).isoformat(timespec="seconds"),
    }])
    if not normalized_items:
        raise ValueError("Conflict resolution decision cannot be empty.")
    item = normalized_items[0]
    existing.append(item)
    save_rule_conflict_resolutions(project_name, layer, existing, story_id, branch_id)
    return item


def delete_rule_conflict_resolution(
    project_name: str,
    layer: str,
    resolution_id: str,
    story_id: str = "default",
    branch_id: str | None = None,
) -> bool:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id, branch_id)
    kept = [item for item in existing if item.get("id") != resolution_id]
    if len(kept) == len(existing):
        return False
    save_rule_conflict_resolutions(project_name, layer, kept, story_id, branch_id)
    return True


def load_effective_rule_conflict_resolutions(project_name: str, story_id: str, scope: str) -> list[dict]:
    effective: list[dict] = []
    layers = [("global", "全局"), ("project", "项目")]
    if str(story_id or "").strip():
        layers.append(("story", "故事"))
    for layer, source_label in layers:
        for item in load_rule_conflict_resolutions(project_name, layer, story_id):
            item_scope = item.get("scope", "all")
            if item_scope in {"all", scope}:
                normalized = dict(item)
                normalized["source"] = source_label
                effective.append(normalized)
    return effective
