"""Creative-profile persistence and approved discussion artifacts."""

from __future__ import annotations

from novelforge.services import memory as _memory_api


def creative_profile_path(project_name: str, story_id: str = "default"):
    return _memory_api._story_path_from_project_path(project_name, story_id, "creative_profile.json")


def load_creative_profile(project_name: str, story_id: str = "default") -> dict:
    db_profile = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_story_profile_row(conn, story_id),
        "creative profile",
    )
    if db_profile is not None:
        return _memory_api.CreativeProfile.model_validate(db_profile).model_dump()
    path = creative_profile_path(project_name, story_id)
    if not path.exists():
        profile = _memory_api.CreativeProfile().model_dump()
        save_creative_profile(project_name, profile, story_id)
        return profile
    try:
        raw = _memory_api.json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    profile = _memory_api.CreativeProfile.model_validate(raw).model_dump()
    if isinstance(raw, dict) and raw and "is_configured" not in raw:
        profile["is_configured"] = True
    if profile != raw:
        save_creative_profile(project_name, profile, story_id)
    elif db_profile == {}:
        _memory_api._sync_runtime_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_story_profile(conn, story_id, profile),
        )
    return profile


def save_creative_profile(
    project_name: str,
    profile: dict,
    story_id: str = "default",
    mark_configured: bool | None = None,
) -> dict:
    normalized = _memory_api.CreativeProfile.model_validate(profile or {}).model_dump()
    if mark_configured is not None:
        normalized["is_configured"] = bool(mark_configured)
    path = creative_profile_path(project_name, story_id)
    _memory_api._write_json_mirror(path, normalized)
    _memory_api._sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: _memory_api.sync_story_profile(conn, story_id, normalized),
    )
    return normalized


def _creative_profile_discussion_path(project_name: str, story_id: str = "default"):
    return _memory_api._story_path_from_project_path(
        project_name,
        story_id,
        "creative_profile.discussion.json",
    )


def save_creative_profile_discussion_artifact(
    project_name: str,
    discussion: dict,
    report_markdown: str,
    story_id: str = "default",
):
    path = _creative_profile_discussion_path(project_name, story_id)
    payload = {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._write_json_mirror(path, payload)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="creative_profile_discussion",
        logical_key="creative_profile",
        story_id=story_id,
        title="Creative Profile Discussion",
        payload=payload,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_creative_profile_discussion_artifact(
    project_name: str,
    story_id: str = "default",
) -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="creative_profile_discussion",
        logical_key="creative_profile",
        story_id=story_id,
    )
    payload = db_payload if isinstance(db_payload, dict) else None
    path = _creative_profile_discussion_path(project_name, story_id)
    if payload is None and not path.exists():
        return {}
    if payload is None:
        try:
            payload = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                path,
                asset_type="creative_profile_discussion",
                logical_key="creative_profile",
                story_id=story_id,
                title="Creative Profile Discussion",
                payload=payload,
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_creative_profile_discussion_artifact(
    project_name: str,
    story_id: str = "default",
) -> bool:
    path = _creative_profile_discussion_path(project_name, story_id)
    existed = path.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="creative_profile_discussion",
        logical_key="creative_profile",
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        path.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="creative_profile_discussion",
        logical_key="creative_profile",
        story_id=story_id,
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return True
