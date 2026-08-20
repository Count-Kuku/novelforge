"""Shared persistence primitives and project-level memory operations."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

import json
import hashlib
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import dotenv_values

from novelforge.core.schemas import (
    ArcOutlineMetadata,
    ChapterOutlineMetadata,
    ConflictResolution,
    ContextDirective,
    CreativeFragment,
    CreativeAttachment,
    CreativeProfile,
    CreativeSession,
    CreativeSessionBundle,
    CreativeTurn,
    StoryMeta,
    StoriesIndex,
    VolumeOutlineMetadata,
)
from novelforge.core.prompt_options import normalize_prompt_options_payload
from novelforge.core.cost_currency import cost_display_preferences
from .runtime_storage import (
    _load_runtime_from_db_best_effort,
    _mutate_workflow_in_db,
    _recover_existing_project_db_if_needed,
    _sync_runtime_to_db_best_effort,
)
from storage import (
    initialize_global_db,
    initialize_project_db,
    inspect_global_db,
    inspect_project_db,
    open_existing_project_db,
    open_global_db,
    open_project_db,
)
from storage.repositories import (
    claim_next_source_ingestion_task_row,
    claim_source_ingestion_task_row,
    cleanup_archived_source_ingestion_task_rows,
    append_retrieval_feedback_row,
    begin_creative_turn_row,
    complete_creative_turn_row,
    create_creative_session_row,
    delete_creative_session_row,
    delete_knowledge_category_item,
    delete_pending_knowledge_items,
    delete_workflow_run_snapshot,
    delete_archived_source_ingestion_task_row,
    fail_creative_turn_row,
    finalize_creative_session_rows,
    get_project_meta,
    load_global_setting,
    load_asset_payload,
    load_creative_fragment_row,
    load_creative_session_row,
    load_entity_alias_group_rows,
    load_auto_review_policy_row,
    load_auto_review_run_rows,
    load_conflict_resolution_rows,
    load_prompt_options_payload,
    load_rules_payload,
    load_story_profile_row,
    load_knowledge_category_rows,
    load_pending_knowledge_rows,
    load_retrieval_eval_case_rows,
    load_retrieval_eval_run_rows,
    load_retrieval_feedback_rows,
    load_retrieval_manifest_payload,
    load_retrieval_vector_store_payload,
    list_asset_file_rows,
    list_asset_payload_rows,
    list_creative_fragment_rows,
    list_creative_session_rows,
    list_creative_turn_rows,
    list_retrieval_source_file_rows,
    load_long_reference_batch_row,
    load_long_reference_batch_rows,
    list_workflow_run_ids,
    list_workflow_run_summaries,
    list_source_ingestion_task_rows,
    load_workflow_run_snapshot,
    load_source_ingestion_task_control_row,
    load_source_ingestion_task_row,
    list_story_rows,
    clone_story_storage_rows,
    purge_story_scoped_rows,
    project_maintenance_mode,
    rename_project_meta,
    mark_asset_deleted,
    mark_long_reference_batch_deleted,
    mark_retrieval_source_file_deleted,
    register_asset_file,
    sync_auto_review_policy,
    sync_auto_review_runs,
    sync_conflict_resolution,
    sync_global_setting,
    sync_prompt_options_payload,
    sync_rules_payload,
    sync_story_profile,
    sync_entity_alias_groups,
    sync_knowledge_category,
    sync_pending_knowledge,
    sync_long_reference_batch,
    sync_retrieval_source_file,
    sync_retrieval_eval_cases,
    sync_retrieval_eval_run,
    sync_retrieval_manifest_payload,
    sync_retrieval_vector_store_payload,
    sync_stories_index,
    sync_workflow_run_snapshot,
    heartbeat_source_ingestion_task_row,
    release_source_ingestion_task_lease_row,
    request_source_ingestion_task_control_row,
    set_source_ingestion_task_archived_row,
    set_project_maintenance_mode,
    settle_stale_source_ingestion_controls_row,
    sync_source_ingestion_task_row,
    upsert_asset_payload,
    upsert_knowledge_category_item,
    upsert_pending_knowledge_items,
    upsert_project_meta,
    update_creative_fragment_row,
    update_creative_session_row,
    list_creative_attachment_rows,
    list_all_creative_attachment_rows,
    claim_turn_creative_attachment_rows,
    load_creative_attachment_row,
    release_turn_creative_attachment_rows,
    update_creative_attachment_row,
    upsert_creative_attachment_row,
    claim_creative_action_row,
    insert_creative_action_row,
    insert_creative_config_revision_row,
    insert_creative_message_row,
    list_creative_action_rows,
    list_creative_message_rows,
    load_creative_action_row,
    load_creative_config_revision_row,
    mark_creative_config_revision_reversed_row,
    transition_creative_action_row,
    update_creative_action_row,
)

BASE_DIR = Path("data/projects")
PROJECT_REGISTRY_PATH = BASE_DIR / "index.json"
DELETED_PROJECTS_DIR = Path("data/deleted_projects")
PROJECT_DATA_MARKERS = (
    "stories",
    "memory.json",
    "creative_profile.json",
    "rules.json",
    "prompt_options.json",
    "retrieval",
)
GLOBAL_RULES_PATH = Path("data/global_rules.json")
GLOBAL_PROMPT_OPTIONS_PATH = Path("data/prompt_options.json")
GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH = Path("data/global_rule_conflict_resolutions.json")
ENV_PATH = Path(".env")
LLM_PROFILES_PATH = Path("data/llm_profiles.json")
RULE_SCOPES = ["all", "outline", "chapter_outline", "write", "review", "setting_extraction"]
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
LLM_PROVIDER_TYPES = {
    "auto", "deepseek", "openrouter", "openai", "qwen",
    "siliconflow", "ollama", "openai_compatible",
}
LLM_COST_TRACKING_MODES = {"auto", "provider_reported", "manual", "tokens_only"}
LLM_EMBEDDING_MODES = {"disabled", "same_provider", "separate_provider", "local"}
MANAGED_ENV_KEYS = [
    "LLM_API_KEY",
    "DEEPSEEK_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_EMBEDDING_MODEL",
    "LLM_EMBEDDING_MODE",
    "LLM_EMBEDDING_BASE_URL",
    "LLM_EMBEDDING_API_KEY",
    "LLM_PROVIDER_TYPE",
    "LLM_COST_TRACKING_MODE",
    "LLM_INPUT_PRICE_PER_MILLION",
    "LLM_CACHED_INPUT_PRICE_PER_MILLION",
    "LLM_CACHE_WRITE_PRICE_PER_MILLION",
    "LLM_OUTPUT_PRICE_PER_MILLION",
    "LLM_EMBEDDING_PRICE_PER_MILLION",
    "LLM_PRICING_CURRENCY",
    "LLM_DISPLAY_CURRENCY",
    "LLM_USD_TO_CNY_RATE",
]
DEFAULT_LLM_PROFILE_NAME = "默认配置"
WINDOWS_RESERVED_PATH_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
WINDOWS_INVALID_PATH_CHARS = set('<>:"/\\|?*')
DEFAULT_MEMORY = {
    "title": "",
    "genre": "",
    "canon_mode": "",
    "au_rules": [],
    "world": [],
    "characters": [],
    "relationships": [],
    "timeline": [],
    "foreshadowing": [],
    "active_constraints": [],
    "chapter_summaries": [],
    "locations": [],
    "organizations": [],
    "power_systems": [],
    "relationship_graph": [],
}
MEMORY_META_FIELDS = ("title", "genre")
KNOWLEDGE_CATEGORIES = {
    "characters": "角色知识",
    "items": "物品与道具",
    "abilities": "技能与能力",
    "world_rules": "世界观规则",
    "locations": "地点资料",
    "organizations": "组织资料",
    "timeline_events": "事件与时间线",
    "relationships": "角色关系",
    "writing_style": "写作风格",
    "dialogue_style": "对白风格",
    "narrative_techniques": "写作手法",
    "constraints": "硬性约束",
}
_DB_UNAVAILABLE_PROJECTS: set[str] = set()
_GLOBAL_DB_UNAVAILABLE = False
_PENDING_MIRROR_DELETIONS: list[Path] = []
_PROJECT_DB_BOOTSTRAP_IN_PROGRESS: set[str] = set()
_GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = False


def _write_json_mirrors_enabled() -> bool:
    return str(os.getenv("NOVELFORGE_WRITE_JSON_MIRRORS", "0")).strip().lower() in {"1", "true", "yes", "on"}


def _queue_mirror_deletion(path: Path) -> None:
    if path.exists() and path.is_file() and path not in _PENDING_MIRROR_DELETIONS:
        _PENDING_MIRROR_DELETIONS.append(path)


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _take_pending_mirror_deletions(predicate=None) -> list[Path]:
    if predicate is None:
        pending = list(_PENDING_MIRROR_DELETIONS)
        _PENDING_MIRROR_DELETIONS.clear()
        return pending
    pending: list[Path] = []
    remaining: list[Path] = []
    for path in _PENDING_MIRROR_DELETIONS:
        if predicate(path):
            pending.append(path)
        else:
            remaining.append(path)
    _PENDING_MIRROR_DELETIONS[:] = remaining
    return pending


def _take_global_pending_mirror_deletions() -> list[Path]:
    global_mirrors = {
        LLM_PROFILES_PATH.resolve(),
        GLOBAL_RULES_PATH.resolve(),
        GLOBAL_PROMPT_OPTIONS_PATH.resolve(),
        GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH.resolve(),
    }
    return _take_pending_mirror_deletions(lambda path: path.resolve() in global_mirrors)


def _take_project_pending_mirror_deletions(project_name: str) -> list[Path]:
    root = project_path(project_name).resolve()
    return _take_pending_mirror_deletions(lambda path: _is_relative_to(path, root))


def _delete_pending_mirrors(paths: list[Path]) -> None:
    for path in paths:
        if path.exists() and path.is_file():
            try:
                path.unlink()
            except OSError as exc:
                logging.getLogger("novelforge.storage").warning(
                    "Failed to delete JSON mirror %s; will retry later: %s",
                    path,
                    exc,
                )
                _queue_mirror_deletion(path)


def _discard_pending_mirror_deletion(path: Path) -> None:
    _PENDING_MIRROR_DELETIONS[:] = [item for item in _PENDING_MIRROR_DELETIONS if item != path]


def _write_json_mirror(path: Path, payload) -> None:
    if not _write_json_mirrors_enabled():
        _queue_mirror_deletion(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_mirror(path: Path, content: str) -> None:
    if not _write_json_mirrors_enabled():
        _queue_mirror_deletion(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(content or ""), encoding="utf-8")


def _default_rules() -> dict:
    return {
        "all": [],
        "outline": [],
        "chapter_outline": [],
        "write": [],
        "review": [],
        "setting_extraction": [],
    }


def normalize_rules(rules: dict | None) -> dict:
    normalized = _default_rules()
    if isinstance(rules, dict):
        for scope in RULE_SCOPES:
            value = rules.get(scope, [])
            normalized[scope] = [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
    return normalized


def _default_llm_profile_payload() -> dict:
    return {
        "active_profile_id": None,
        "profiles": [],
    }


def _normalize_llm_profile(profile: dict | None, fallback_id: str) -> dict:
    raw = profile if isinstance(profile, dict) else {}
    profile_id = str(raw.get("id") or fallback_id).strip() or fallback_id
    name = str(raw.get("name") or "").strip() or DEFAULT_LLM_PROFILE_NAME
    def safe_rate(value: object) -> float:
        try:
            parsed = float(value or 0)
        except (TypeError, ValueError):
            return 0.0
        return parsed if math.isfinite(parsed) and parsed >= 0 else 0.0

    provider_type = str(raw.get("provider_type") or "auto").strip().lower() or "auto"
    if provider_type not in LLM_PROVIDER_TYPES:
        provider_type = "auto"
    cost_tracking_mode = str(raw.get("cost_tracking_mode") or "auto").strip().lower() or "auto"
    if cost_tracking_mode not in LLM_COST_TRACKING_MODES:
        cost_tracking_mode = "auto"
    raw_embedding_mode = str(raw.get("embedding_mode") or "").strip().lower()
    if raw_embedding_mode in LLM_EMBEDDING_MODES:
        embedding_mode = raw_embedding_mode
    elif provider_type in {"deepseek", "openrouter"} or any(
        marker in str(raw.get("base_url") or "").lower()
        for marker in ("api.deepseek.com", "openrouter.ai")
    ):
        embedding_mode = "disabled"
    else:
        embedding_mode = "same_provider"
    embedding_model_name = str(raw.get("embedding_model_name") or "").strip()
    if embedding_mode != "disabled" and not embedding_model_name:
        embedding_model_name = DEFAULT_EMBEDDING_MODEL
    currency_preferences = cost_display_preferences(raw)

    return {
        "id": profile_id,
        "name": name,
        "base_url": str(raw.get("base_url") or DEFAULT_LLM_BASE_URL),
        "api_key": str(raw.get("api_key") or ""),
        "api_key_ref": str(raw.get("api_key_ref") or "").strip(),
        "api_key_fingerprint": str(raw.get("api_key_fingerprint") or "").strip(),
        "api_key_last_four": str(raw.get("api_key_last_four") or "").strip(),
        "api_key_backend": str(raw.get("api_key_backend") or "").strip(),
        "model_name": str(raw.get("model_name") or DEFAULT_LLM_MODEL),
        "embedding_mode": embedding_mode,
        "embedding_model_name": embedding_model_name,
        "embedding_base_url": str(raw.get("embedding_base_url") or "").strip(),
        "embedding_api_key": str(raw.get("embedding_api_key") or ""),
        "embedding_api_key_ref": str(raw.get("embedding_api_key_ref") or "").strip(),
        "embedding_api_key_fingerprint": str(raw.get("embedding_api_key_fingerprint") or "").strip(),
        "embedding_api_key_last_four": str(raw.get("embedding_api_key_last_four") or "").strip(),
        "embedding_api_key_backend": str(raw.get("embedding_api_key_backend") or "").strip(),
        "provider_type": provider_type,
        "cost_tracking_mode": cost_tracking_mode,
        **currency_preferences,
        "input_price_per_million": safe_rate(raw.get("input_price_per_million")),
        "cached_input_price_per_million": safe_rate(raw.get("cached_input_price_per_million")),
        "cache_write_price_per_million": safe_rate(raw.get("cache_write_price_per_million")),
        "output_price_per_million": safe_rate(raw.get("output_price_per_million")),
        "embedding_price_per_million": safe_rate(raw.get("embedding_price_per_million")),
        "pricing_updated_at": str(raw.get("pricing_updated_at") or "").strip(),
        "pricing_source_url": str(raw.get("pricing_source_url") or "").strip(),
        "chat_status": str(raw.get("chat_status") or "unverified").strip() or "unverified",
        "embedding_status": str(raw.get("embedding_status") or "unverified").strip() or "unverified",
        "capabilities_verified_at": str(raw.get("capabilities_verified_at") or "").strip(),
        "chat_status_message": str(raw.get("chat_status_message") or "").strip(),
        "embedding_status_message": str(raw.get("embedding_status_message") or "").strip(),
        "preflight_enabled": bool(raw.get("preflight_enabled", True)),
        "preflight_warning_tokens": int(safe_rate(raw.get("preflight_warning_tokens", 50000))),
        "preflight_confirmation_tokens": int(
            safe_rate(raw.get("preflight_confirmation_tokens", 150000))
        ),
        "preflight_warning_cost_usd": safe_rate(raw.get("preflight_warning_cost_usd", 0.05)),
        "preflight_confirmation_cost_usd": safe_rate(raw.get("preflight_confirmation_cost_usd", 0.25)),
        "preflight_warning_cost_cny": safe_rate(raw.get("preflight_warning_cost_cny", 0.5)),
        "preflight_confirmation_cost_cny": safe_rate(raw.get("preflight_confirmation_cost_cny", 2.0)),
        "preflight_require_confirmation": bool(
            raw.get("preflight_require_confirmation", False)
        ),
    }


def _normalize_llm_profiles_payload(payload: dict | None) -> dict:
    raw_payload = payload if isinstance(payload, dict) else _default_llm_profile_payload()
    raw_profiles = raw_payload.get("profiles", []) if isinstance(raw_payload, dict) else []
    normalized_profiles: list[dict] = []
    seen_ids: set[str] = set()
    for index, profile in enumerate(raw_profiles, start=1):
        normalized = _normalize_llm_profile(profile, f"profile_{index:03d}")
        if normalized["id"] in seen_ids:
            normalized["id"] = f"{normalized['id']}_{index:03d}"
        seen_ids.add(normalized["id"])
        normalized_profiles.append(normalized)

    if not normalized_profiles:
        normalized_profiles = [_load_env_llm_profile()]

    active_profile_id = str(raw_payload.get("active_profile_id") or "").strip()
    if active_profile_id not in {profile["id"] for profile in normalized_profiles}:
        active_profile_id = normalized_profiles[0]["id"]

    return {
        "active_profile_id": active_profile_id,
        "profiles": normalized_profiles,
    }


def _hydrate_llm_profiles_payload(payload: dict) -> dict:
    from .model_credentials import hydrate_llm_profiles_safely

    return hydrate_llm_profiles_safely(payload, _normalize_llm_profiles_payload)


def _persist_llm_profiles_payload(payload: dict) -> dict:
    from .model_credentials import persist_llm_profiles_payload

    return persist_llm_profiles_payload(
        payload,
        normalize=_normalize_llm_profiles_payload,
        global_db_unavailable=_global_db_marked_unavailable,
        write_json_mirror=_write_json_mirror,
        profiles_path=LLM_PROFILES_PATH,
        env_path=ENV_PATH,
    )


def _load_env_llm_profile() -> dict:
    file_values = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    api_key = (
        os.getenv("LLM_API_KEY")
        or file_values.get("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or file_values.get("DEEPSEEK_API_KEY")
        or ""
    )
    base_url = os.getenv("LLM_BASE_URL") or file_values.get("LLM_BASE_URL") or DEFAULT_LLM_BASE_URL
    model_name = os.getenv("LLM_MODEL") or file_values.get("LLM_MODEL") or DEFAULT_LLM_MODEL
    embedding_model_name = (
        os.getenv("LLM_EMBEDDING_MODEL")
        or file_values.get("LLM_EMBEDDING_MODEL")
        or os.getenv("EMBEDDING_MODEL")
        or file_values.get("EMBEDDING_MODEL")
        or ""
    )
    embedding_mode = (
        os.getenv("LLM_EMBEDDING_MODE")
        or file_values.get("LLM_EMBEDDING_MODE")
        or ""
    )
    return _normalize_llm_profile(
        {
            "id": "default",
            "name": DEFAULT_LLM_PROFILE_NAME,
            "base_url": base_url,
            "api_key": api_key,
            "model_name": model_name,
            "embedding_model_name": embedding_model_name,
            "embedding_mode": embedding_mode,
            "embedding_base_url": os.getenv("LLM_EMBEDDING_BASE_URL") or file_values.get("LLM_EMBEDDING_BASE_URL") or "",
            "embedding_api_key": os.getenv("LLM_EMBEDDING_API_KEY") or file_values.get("LLM_EMBEDDING_API_KEY") or "",
            "provider_type": os.getenv("LLM_PROVIDER_TYPE") or file_values.get("LLM_PROVIDER_TYPE") or "auto",
            "cost_tracking_mode": os.getenv("LLM_COST_TRACKING_MODE") or file_values.get("LLM_COST_TRACKING_MODE") or "auto",
            "pricing_currency": os.getenv("LLM_PRICING_CURRENCY") or file_values.get("LLM_PRICING_CURRENCY") or "USD",
            "display_currency": os.getenv("LLM_DISPLAY_CURRENCY") or file_values.get("LLM_DISPLAY_CURRENCY") or "CNY",
            "usd_to_cny_rate": os.getenv("LLM_USD_TO_CNY_RATE") or file_values.get("LLM_USD_TO_CNY_RATE") or 7.142857,
            "input_price_per_million": os.getenv("LLM_INPUT_PRICE_PER_MILLION") or file_values.get("LLM_INPUT_PRICE_PER_MILLION") or 0,
            "cached_input_price_per_million": os.getenv("LLM_CACHED_INPUT_PRICE_PER_MILLION") or file_values.get("LLM_CACHED_INPUT_PRICE_PER_MILLION") or 0,
            "cache_write_price_per_million": os.getenv("LLM_CACHE_WRITE_PRICE_PER_MILLION") or file_values.get("LLM_CACHE_WRITE_PRICE_PER_MILLION") or 0,
            "output_price_per_million": os.getenv("LLM_OUTPUT_PRICE_PER_MILLION") or file_values.get("LLM_OUTPUT_PRICE_PER_MILLION") or 0,
            "embedding_price_per_million": os.getenv("LLM_EMBEDDING_PRICE_PER_MILLION") or file_values.get("LLM_EMBEDDING_PRICE_PER_MILLION") or 0,
        },
        "default",
    )


def load_llm_profiles() -> dict:
    db_payload = _load_global_from_db_best_effort(
        lambda conn: load_global_setting(conn, "llm_profiles"),
        "LLM profiles",
    )
    if isinstance(db_payload, dict):
        from .model_credentials import scrub_legacy_model_secrets_safely

        scrub_legacy_model_secrets_safely(ENV_PATH)
        normalized = _normalize_llm_profiles_payload(db_payload)
        if any(
            profile.get("api_key") or profile.get("embedding_api_key")
            for profile in normalized.get("profiles", [])
        ):
            try:
                db_payload = _persist_llm_profiles_payload(normalized)
            except Exception as exc:
                # A headless Windows process can temporarily lack a logon
                # session for Credential Manager. Keep the already-persisted
                # legacy profile usable in memory and retry migration on the
                # next load; never write a new raw secret in this path.
                logging.getLogger("novelforge.credentials").warning(
                    "Legacy model credential migration deferred: %s", exc
                )
                return normalized
        return _hydrate_llm_profiles_payload(db_payload)

    LLM_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LLM_PROFILES_PATH.exists():
        env_profile = _load_env_llm_profile()
        payload = {
            "active_profile_id": env_profile["id"],
            "profiles": [env_profile],
        }
        secured = _persist_llm_profiles_payload(payload)
        return _hydrate_llm_profiles_payload(secured)

    try:
        raw_payload = json.loads(LLM_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw_payload = _default_llm_profile_payload()

    payload = _normalize_llm_profiles_payload(raw_payload)
    secured = _persist_llm_profiles_payload(payload)
    return _hydrate_llm_profiles_payload(secured)


def save_llm_profiles(payload: dict):
    _persist_llm_profiles_payload(payload)


def get_active_llm_profile() -> dict:
    payload = load_llm_profiles()
    active_profile_id = payload.get("active_profile_id")
    for profile in payload.get("profiles", []):
        if profile.get("id") == active_profile_id:
            return dict(profile)
    return dict(payload.get("profiles", [{}])[0])


def load_llm_settings() -> dict:
    active_profile = get_active_llm_profile()
    return {
        "profile_id": str(active_profile.get("id") or ""),
        "profile_name": str(active_profile.get("name") or DEFAULT_LLM_PROFILE_NAME),
        "api_key": str(active_profile.get("api_key") or ""),
        "api_key_ref": str(active_profile.get("api_key_ref") or ""),
        "api_key_last_four": str(active_profile.get("api_key_last_four") or ""),
        "api_key_backend": str(active_profile.get("api_key_backend") or ""),
        "base_url": str(active_profile.get("base_url") or DEFAULT_LLM_BASE_URL),
        "model_name": str(active_profile.get("model_name") or DEFAULT_LLM_MODEL),
        "embedding_mode": str(active_profile.get("embedding_mode") or "disabled"),
        "embedding_model_name": str(active_profile.get("embedding_model_name") or ""),
        "embedding_base_url": str(active_profile.get("embedding_base_url") or ""),
        "embedding_api_key": str(active_profile.get("embedding_api_key") or ""),
        "embedding_api_key_ref": str(active_profile.get("embedding_api_key_ref") or ""),
        "embedding_api_key_last_four": str(active_profile.get("embedding_api_key_last_four") or ""),
        "provider_type": str(active_profile.get("provider_type") or "auto"),
        "cost_tracking_mode": str(active_profile.get("cost_tracking_mode") or "auto"),
        **cost_display_preferences(active_profile),
        "input_price_per_million": float(active_profile.get("input_price_per_million") or 0),
        "cached_input_price_per_million": float(active_profile.get("cached_input_price_per_million") or 0),
        "cache_write_price_per_million": float(active_profile.get("cache_write_price_per_million") or 0),
        "output_price_per_million": float(active_profile.get("output_price_per_million") or 0),
        "embedding_price_per_million": float(active_profile.get("embedding_price_per_million") or 0),
        "pricing_updated_at": str(active_profile.get("pricing_updated_at") or ""),
        "pricing_source_url": str(active_profile.get("pricing_source_url") or ""),
        "chat_status": str(active_profile.get("chat_status") or "unverified"),
        "embedding_status": str(active_profile.get("embedding_status") or "unverified"),
        "capabilities_verified_at": str(active_profile.get("capabilities_verified_at") or ""),
        "chat_status_message": str(active_profile.get("chat_status_message") or ""),
        "embedding_status_message": str(active_profile.get("embedding_status_message") or ""),
        "preflight_enabled": bool(active_profile.get("preflight_enabled", True)),
        "preflight_warning_tokens": int(active_profile.get("preflight_warning_tokens") or 0),
        "preflight_confirmation_tokens": int(
            active_profile.get("preflight_confirmation_tokens") or 0
        ),
        "preflight_warning_cost_usd": float(
            active_profile.get("preflight_warning_cost_usd") or 0
        ),
        "preflight_confirmation_cost_usd": float(
            active_profile.get("preflight_confirmation_cost_usd") or 0
        ),
        "preflight_warning_cost_cny": float(
            active_profile.get("preflight_warning_cost_cny") or 0
        ),
        "preflight_confirmation_cost_cny": float(
            active_profile.get("preflight_confirmation_cost_cny") or 0
        ),
        "preflight_require_confirmation": bool(
            active_profile.get("preflight_require_confirmation", False)
        ),
        "env_path": str(ENV_PATH.resolve()),
        "profiles_path": str(LLM_PROFILES_PATH.resolve()),
    }


def _serialize_env_value(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if any(char in text for char in [' ', '#', '"', "'", '\t']):
        return json.dumps(text, ensure_ascii=False)
    return text


def save_llm_settings(settings: dict):
    provider_type = str(settings.get("provider_type", "auto") or "auto").strip().lower()
    base_url = str(settings.get("base_url", "") or "")
    normalized = {
        # Secrets live in the system credential manager.  Blank legacy entries
        # also scrub keys left behind by older releases.
        "LLM_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": str(settings.get("model_name", "") or ""),
        "LLM_EMBEDDING_MODEL": str(settings.get("embedding_model_name", "") or ""),
        "LLM_EMBEDDING_MODE": str(settings.get("embedding_mode", "disabled") or "disabled"),
        "LLM_EMBEDDING_BASE_URL": str(settings.get("embedding_base_url", "") or ""),
        "LLM_EMBEDDING_API_KEY": "",
        "LLM_PROVIDER_TYPE": str(settings.get("provider_type", "auto") or "auto"),
        "LLM_COST_TRACKING_MODE": str(settings.get("cost_tracking_mode", "auto") or "auto"),
        "LLM_PRICING_CURRENCY": str(settings.get("pricing_currency", "USD") or "USD"),
        "LLM_DISPLAY_CURRENCY": str(settings.get("display_currency", "CNY") or "CNY"),
        "LLM_USD_TO_CNY_RATE": str(settings.get("usd_to_cny_rate", 7.142857) or 7.142857),
        "LLM_INPUT_PRICE_PER_MILLION": str(settings.get("input_price_per_million", 0) or 0),
        "LLM_CACHED_INPUT_PRICE_PER_MILLION": str(settings.get("cached_input_price_per_million", 0) or 0),
        "LLM_CACHE_WRITE_PRICE_PER_MILLION": str(settings.get("cache_write_price_per_million", 0) or 0),
        "LLM_OUTPUT_PRICE_PER_MILLION": str(settings.get("output_price_per_million", 0) or 0),
        "LLM_EMBEDDING_PRICE_PER_MILLION": str(settings.get("embedding_price_per_million", 0) or 0),
    }
    env_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=")
    updated_lines: list[str] = []
    seen_keys: set[str] = set()

    for line in env_lines:
        match = pattern.match(line)
        if not match:
            updated_lines.append(line)
            continue

        key = match.group(1)
        if key not in normalized:
            updated_lines.append(line)
            continue
        if key in seen_keys:
            continue

        updated_lines.append(f"{key}={_serialize_env_value(normalized[key])}")
        seen_keys.add(key)

    if updated_lines and updated_lines[-1].strip():
        updated_lines.append("")
    if not env_lines:
        updated_lines.extend([
            "# Managed by NovelForge UI",
        ])

    for key in MANAGED_ENV_KEYS:
        if key in seen_keys:
            continue
        updated_lines.append(f"{key}={_serialize_env_value(normalized[key])}")

    ENV_PATH.write_text("\n".join(updated_lines).rstrip() + "\n", encoding="utf-8")

    for key, value in normalized.items():
        if value:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
    try:
        from novelforge.core.llm import clear_llm_client_cache

        clear_llm_client_cache()
    except Exception as exc:
        import logging

        logging.getLogger("novelforge").warning("Failed to clear LLM client cache: %s", exc)


def set_active_llm_profile(profile_id: str):
    payload = load_llm_profiles()
    target_id = str(profile_id or "").strip()
    for profile in payload.get("profiles", []):
        if profile.get("id") != target_id:
            continue
        payload["active_profile_id"] = target_id
        save_llm_profiles(payload)
        save_llm_settings(profile)
        return dict(profile)
    raise ValueError("LLM profile not found.")


def upsert_llm_profile(profile: dict) -> dict:
    payload = load_llm_profiles()
    target_id = str(profile.get("id") or "").strip()
    existing_profile = next(
        (item for item in payload.get("profiles", []) if item.get("id") == target_id),
        {},
    )
    merged_profile = {**existing_profile, **dict(profile or {})}
    for secret_field in ("api_key", "embedding_api_key"):
        if not str(profile.get(secret_field) or "").strip() and existing_profile:
            merged_profile[secret_field] = existing_profile.get(secret_field, "")
            for suffix in ("ref", "fingerprint", "last_four", "backend"):
                ref_field = f"{secret_field}_{suffix}"
                merged_profile[ref_field] = existing_profile.get(ref_field, "")
    normalized = _normalize_llm_profile(
        merged_profile,
        target_id or f"profile_{len(payload.get('profiles', [])) + 1:03d}",
    )

    updated_profiles: list[dict] = []
    replaced = False
    for existing in payload.get("profiles", []):
        if existing.get("id") == normalized["id"]:
            updated_profiles.append(normalized)
            replaced = True
        else:
            updated_profiles.append(existing)
    if not replaced:
        updated_profiles.append(normalized)

    payload["profiles"] = updated_profiles
    if not payload.get("active_profile_id"):
        payload["active_profile_id"] = normalized["id"]
    save_llm_profiles(payload)
    if payload.get("active_profile_id") == normalized["id"]:
        save_llm_settings(normalized)
    return normalized


def delete_llm_profile(profile_id: str) -> dict:
    payload = load_llm_profiles()
    target_id = str(profile_id or "").strip()
    removed_profiles = [profile for profile in payload.get("profiles", []) if profile.get("id") == target_id]
    remaining_profiles = [profile for profile in payload.get("profiles", []) if profile.get("id") != target_id]
    if len(remaining_profiles) == len(payload.get("profiles", [])):
        raise ValueError("LLM profile not found.")
    if not remaining_profiles:
        raise ValueError("At least one LLM profile must remain.")

    payload["profiles"] = remaining_profiles
    if payload.get("active_profile_id") == target_id:
        payload["active_profile_id"] = remaining_profiles[0]["id"]
    save_llm_profiles(payload)
    from novelforge.services.credentials import delete_system_credential

    for removed in removed_profiles:
        for field in ("api_key_ref", "embedding_api_key_ref"):
            credential_ref = str(removed.get(field) or "").strip()
            if credential_ref:
                delete_system_credential(credential_ref)
    active_profile = get_active_llm_profile()
    save_llm_settings(active_profile)
    return payload


def normalize_project_name(project_name: str) -> str:
    normalized = project_name.strip()
    if not normalized:
        raise ValueError("Project name cannot be empty.")
    if (
        normalized in {".", ".."}
        or ".." in normalized
        or any(char in WINDOWS_INVALID_PATH_CHARS for char in normalized)
        or any(ord(char) < 32 for char in normalized)
        or normalized.endswith(".")
        or normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED_PATH_NAMES
    ):
        raise ValueError("Invalid project name: path traversal characters not allowed.")
    return normalized


def normalize_storage_component(value: str, label: str = "Storage key") -> str:
    """Validate a user/data supplied value before using it in a filename."""

    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} cannot be empty.")
    if (
        normalized in {".", ".."}
        or any(char in WINDOWS_INVALID_PATH_CHARS for char in normalized)
        or any(ord(char) < 32 for char in normalized)
        or normalized.endswith(".")
        or normalized.split(".", 1)[0].upper() in WINDOWS_RESERVED_PATH_NAMES
    ):
        raise ValueError(f"Invalid {label.lower()}: path characters are not allowed.")
    return normalized


def project_dir(project_name: str) -> Path:
    return BASE_DIR / normalize_project_name(project_name)


def project_path(project_name: str) -> Path:
    return project_dir(project_name)


def ensure_project_path(project_name: str) -> Path:
    path = project_dir(project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_data_exists(project_name: str) -> bool:
    return project_dir(project_name).is_dir()


def _project_registry_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _normalize_project_registry(payload: dict | None) -> dict:
    raw_payload = payload if isinstance(payload, dict) else {}
    raw_projects = raw_payload.get("projects", [])
    projects: list[dict] = []
    seen: set[str] = set()
    if isinstance(raw_projects, list):
        for item in raw_projects:
            raw = item if isinstance(item, dict) else {"name": item}
            try:
                name = normalize_project_name(str(raw.get("name") or ""))
            except ValueError:
                continue
            if name in seen:
                continue
            seen.add(name)
            now = _project_registry_now()
            projects.append({
                "name": name,
                "status": str(raw.get("status") or "active"),
                "created_at": str(raw.get("created_at") or now),
                "updated_at": str(raw.get("updated_at") or now),
            })

    try:
        active_project = normalize_project_name(str(raw_payload.get("active_project") or ""))
    except ValueError:
        active_project = ""

    return {
        "version": 1,
        "active_project": active_project,
        "projects": projects,
    }


def _project_db_marker_is_valid(path: Path) -> bool:
    try:
        return path.is_file() and path.stat().st_size > 0
    except OSError:
        return False


def _project_dir_looks_like_project(path: Path) -> bool:
    if not path.is_dir():
        return False
    if path.name.startswith("."):
        return False
    if any((path / marker).exists() for marker in PROJECT_DATA_MARKERS):
        return True
    return _project_db_marker_is_valid(path / "project.db")


def _discover_legacy_project_names() -> list[str]:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    names: list[str] = []
    for path in BASE_DIR.iterdir():
        if not _project_dir_looks_like_project(path):
            continue
        try:
            names.append(normalize_project_name(path.name))
        except ValueError:
            continue
    return sorted(set(names), key=str.lower)


def _save_project_registry(registry: dict) -> dict:
    normalized = _normalize_project_registry(registry)
    PROJECT_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROJECT_REGISTRY_PATH.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def _backup_corrupt_project_registry(exc: Exception) -> None:
    if not PROJECT_REGISTRY_PATH.exists():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = PROJECT_REGISTRY_PATH.with_name(f"{PROJECT_REGISTRY_PATH.name}.corrupt-{timestamp}")
    counter = 1
    while backup_path.exists():
        backup_path = PROJECT_REGISTRY_PATH.with_name(f"{PROJECT_REGISTRY_PATH.name}.corrupt-{timestamp}-{counter}")
        counter += 1
    try:
        PROJECT_REGISTRY_PATH.replace(backup_path)
    except OSError:
        logging.getLogger("novelforge.storage").warning(
            "Failed to back up corrupt project registry %s after %s",
            PROJECT_REGISTRY_PATH,
            exc,
        )
    else:
        logging.getLogger("novelforge.storage").warning(
            "Backed up corrupt project registry %s to %s after %s",
            PROJECT_REGISTRY_PATH,
            backup_path,
            exc,
        )


def _build_project_registry_from_directories() -> dict:
    project_names = _discover_legacy_project_names()
    now = _project_registry_now()
    return {
        "version": 1,
        "active_project": "",
        "projects": [
            {"name": name, "status": "active", "created_at": now, "updated_at": now}
            for name in project_names
        ],
    }


def load_project_registry() -> dict:
    if PROJECT_REGISTRY_PATH.exists():
        try:
            raw = json.loads(PROJECT_REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as exc:
            _backup_corrupt_project_registry(exc)
            return _save_project_registry(_build_project_registry_from_directories())
        registry = _normalize_project_registry(raw)
        if raw != registry:
            registry = _save_project_registry(registry)
        return registry

    return _save_project_registry(_build_project_registry_from_directories())


def restore_project_registry(registry: dict) -> dict:
    """Restore a previously loaded registry snapshot during compensation."""

    return _save_project_registry(registry)


def list_projects() -> list[str]:
    return _discover_legacy_project_names()


def project_is_discoverable(project_name: str) -> bool:
    try:
        normalized_name = normalize_project_name(project_name)
    except ValueError:
        return False
    return _project_dir_looks_like_project(project_dir(normalized_name))


def project_is_registered(project_name: str) -> bool:
    return project_is_discoverable(project_name)


def register_project(project_name: str, *, make_active: bool = False) -> str:
    normalized_name = normalize_project_name(project_name)
    registry = load_project_registry()
    now = _project_registry_now()
    updated = False
    for item in registry.get("projects", []):
        if item.get("name") == normalized_name:
            item["status"] = "active"
            item["updated_at"] = now
            updated = True
            break
    if not updated:
        registry.setdefault("projects", []).append({
            "name": normalized_name,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
    if make_active:
        registry["active_project"] = normalized_name
    _save_project_registry(registry)
    return normalized_name


def unregister_project(project_name: str) -> bool:
    normalized_name = normalize_project_name(project_name)
    registry = load_project_registry()
    original_projects = list(registry.get("projects", []))
    registry["projects"] = [item for item in original_projects if item.get("name") != normalized_name]
    removed = len(registry["projects"]) != len(original_projects)
    if registry.get("active_project") == normalized_name:
        registry["active_project"] = ""
    _save_project_registry(registry)
    return removed


def rename_registered_project(old_name: str, new_name: str) -> str:
    old_normalized = normalize_project_name(old_name)
    new_normalized = normalize_project_name(new_name)
    registry = load_project_registry()
    if old_normalized != new_normalized:
        registry["projects"] = [
            item for item in registry.get("projects", []) if item.get("name") != new_normalized
        ]
    now = _project_registry_now()
    renamed = False
    for item in registry.get("projects", []):
        if item.get("name") == old_normalized:
            item["name"] = new_normalized
            item["updated_at"] = now
            renamed = True
            break
    if registry.get("active_project") == old_normalized:
        registry["active_project"] = new_normalized
    if not renamed:
        registry.setdefault("projects", []).append({
            "name": new_normalized,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        })
    _save_project_registry(registry)
    return new_normalized


def get_active_project_name() -> str:
    registry = load_project_registry()
    active_project = str(registry.get("active_project") or "").strip()
    return active_project if active_project in set(list_projects()) else ""


def set_active_project_name(project_name: str | None) -> None:
    registry = load_project_registry()
    if project_name:
        normalized_name = normalize_project_name(project_name)
        if normalized_name not in set(list_projects()):
            return
        registry["active_project"] = normalized_name
    else:
        registry["active_project"] = ""
    _save_project_registry(registry)


def inspect_project_database(project_name: str) -> dict:
    return inspect_project_db(project_dir(project_name))


def inspect_global_database() -> dict:
    return inspect_global_db(Path("data"))


def rename_project_database_record(project_name: str, old_name: str, new_name: str) -> dict:
    """Rename the project metadata row inside an already moved project DB."""

    normalized_project_name = normalize_project_name(project_name)
    normalized_old_name = normalize_project_name(old_name)
    normalized_new_name = normalize_project_name(new_name)
    with open_project_db(project_path(normalized_project_name).resolve()) as conn:
        result = rename_project_meta(conn, normalized_old_name, normalized_new_name)
        conn.commit()
    return result


def set_project_maintenance(project_name: str, enabled: bool) -> bool:
    """Atomically fence or reopen background work for a project."""
    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Project does not exist: {normalized_name}")
    _bootstrap_project_database_if_needed(normalized_name)
    with open_existing_project_db(root) as conn:
        conn.execute("BEGIN IMMEDIATE")
        changed = set_project_maintenance_mode(conn, normalized_name, enabled)
        conn.commit()
    return changed


def is_project_in_maintenance(project_name: str) -> bool:
    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name).resolve()
    if not root.is_dir():
        return False
    _bootstrap_project_database_if_needed(normalized_name)
    with open_existing_project_db(root) as conn:
        return project_maintenance_mode(conn, normalized_name)


def _db_only_storage_required() -> bool:
    return not _write_json_mirrors_enabled()


def _raise_if_db_only(message: str, exc: Exception | None = None) -> None:
    if not _db_only_storage_required():
        return
    if exc is None:
        raise RuntimeError(message)
    raise RuntimeError(message) from exc


def _project_db_marked_unavailable(project_name: str) -> bool:
    _bootstrap_project_database_if_needed(project_name)
    if project_name not in _DB_UNAVAILABLE_PROJECTS:
        return False
    _initialize_project_db_best_effort(project_name)
    if project_name not in _DB_UNAVAILABLE_PROJECTS:
        return False
    _raise_if_db_only(f"Project database is unavailable for {project_name}.")
    return True

def _global_db_marked_unavailable() -> bool:
    _bootstrap_global_database_if_needed()
    if not _GLOBAL_DB_UNAVAILABLE:
        return False
    _initialize_global_db_best_effort()
    if not _GLOBAL_DB_UNAVAILABLE:
        return False
    _raise_if_db_only("Global database is unavailable.")
    return True


def _bootstrap_project_database_if_needed(project_name: str) -> None:
    """Import a legacy file-backed project before the first DB-first read.

    Opening SQLite creates an empty database.  If that happens before legacy
    JSON has been imported, valid file-backed data is indistinguishable from
    an intentionally empty authoritative database and is silently hidden.
    """

    normalized_name = normalize_project_name(project_name)
    root = project_path(normalized_name)
    db_path = root / "project.db"
    if normalized_name in _PROJECT_DB_BOOTSTRAP_IN_PROGRESS:
        return
    if not root.exists() or not _project_dir_looks_like_project(root):
        return
    if db_path.exists():
        try:
            if db_path.stat().st_size > 0:
                return
        except OSError:
            return
        raise RuntimeError(
            f"Legacy project {normalized_name} has a zero-byte project.db. "
            "Automatic import was stopped to avoid racing a running app. "
            "Close NovelForge, move the empty database aside, then reopen the project."
        )

    _PROJECT_DB_BOOTSTRAP_IN_PROGRESS.add(normalized_name)
    try:
        result = _memory_api.sync_project_database_from_files(normalized_name)
        if not result.get("ok"):
            error = str(result.get("error") or "unknown legacy import error")
            raise RuntimeError(f"Failed to import legacy project storage for {normalized_name}: {error}")
    finally:
        _PROJECT_DB_BOOTSTRAP_IN_PROGRESS.discard(normalized_name)


def _bootstrap_global_database_if_needed() -> None:
    """Import legacy global JSON/.env settings before creating global.db."""

    global _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS
    database_path = Path("data") / "global.db"
    if _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS:
        return
    if database_path.exists():
        try:
            if database_path.stat().st_size > 0:
                return
        except OSError:
            return
        raise RuntimeError(
            "data/global.db is zero bytes. Automatic import was stopped to avoid "
            "racing a running app. Close NovelForge, move the empty database aside, "
            "then restart."
        )
    _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = True
    try:
        result = _memory_api.sync_global_database_from_files()
        if not result.get("ok"):
            error = str(result.get("error") or "unknown legacy import error")
            raise RuntimeError(f"Failed to import legacy global storage: {error}")
    finally:
        _GLOBAL_DB_BOOTSTRAP_IN_PROGRESS = False


def _initialize_global_db_best_effort() -> None:
    global _GLOBAL_DB_UNAVAILABLE
    try:
        initialize_global_db(Path("data"))
        _GLOBAL_DB_UNAVAILABLE = False
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to initialize global database: %s",
            exc,
        )
        _raise_if_db_only("Failed to initialize global database.", exc)


def _sync_global_to_db_best_effort(callback) -> None:
    global _GLOBAL_DB_UNAVAILABLE
    if _global_db_marked_unavailable():
        return
    try:
        with open_global_db(Path("data")) as conn:
            callback(conn)
            conn.commit()
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync global record to database: %s",
            exc,
        )
        _raise_if_db_only("Failed to sync global record to database.", exc)
    else:
        _delete_pending_mirrors(_take_global_pending_mirror_deletions())


def _load_global_from_db_best_effort(loader, description: str):
    global _GLOBAL_DB_UNAVAILABLE
    if _global_db_marked_unavailable():
        return None
    try:
        with open_global_db(Path("data")) as conn:
            return loader(conn)
    except Exception as exc:
        _GLOBAL_DB_UNAVAILABLE = True
        logging.getLogger("novelforge.storage").warning(
            "Failed to load %s from global database: %s",
            description,
            exc,
        )
        _raise_if_db_only(f"Failed to load {description} from global database.", exc)
        return None


def _initialize_project_db_best_effort(project_name: str) -> None:
    try:
        initialize_project_db(ensure_project_path(project_name), project_name)
        _DB_UNAVAILABLE_PROJECTS.discard(project_name)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to initialize project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to initialize project database for {project_name}.", exc)


def _sync_stories_index_to_db_best_effort(project_name: str, index: dict) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name)) as conn:
            sync_stories_index(conn, index)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync stories index to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync stories index to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def _load_stories_index_from_db_best_effort(project_name: str) -> dict | None:
    if _project_db_marked_unavailable(project_name):
        return None
    try:
        with open_project_db(project_path(project_name)) as conn:
            rows = list_story_rows(conn)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load stories index from project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to load stories index from project database for {project_name}.", exc)
        return None
    if not rows:
        return {"stories": [], "active_story_id": "default"}
    stories = [
        {
            "story_id": str(row.get("story_id") or ""),
            "name": str(row.get("name") or row.get("story_id") or ""),
            "description": str(row.get("description") or ""),
            "status": str(row.get("status") or "active"),
            "creation_mode": str(row.get("creation_mode") or "planned"),
            "created_at": str(row.get("created_at") or ""),
            "updated_at": str(row.get("updated_at") or ""),
        }
        for row in rows
        if str(row.get("story_id") or "").strip()
    ]
    active_story_id = "default"
    for row in rows:
        if row.get("is_active"):
            active_story_id = str(row.get("story_id") or "default")
            break
    if not any(story["story_id"] == active_story_id for story in stories):
        active_story_id = stories[0]["story_id"] if stories else "default"
    return StoriesIndex(stories=stories, active_story_id=active_story_id).model_dump()


def _register_asset_file_best_effort(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
    title: str = "",
    mime_type: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        root = project_path(project_name).resolve()
        resolved_file = file.resolve()
        relative_path = str(resolved_file.relative_to(root)).replace("\\", "/")
        content_hash = ""
        if resolved_file.exists() and resolved_file.is_file():
            content_hash = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
        asset_id_source = f"{story_id or 'project'}:{asset_type}:{logical_key}"
        asset_id = "asset_" + hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
        with open_project_db(root) as conn:
            register_asset_file(
                conn,
                asset_id=asset_id,
                story_id=story_id,
                asset_type=asset_type,
                logical_key=logical_key,
                title=title,
                relative_path=relative_path,
                content_hash=content_hash or None,
                mime_type=mime_type,
                source_kind=source_kind,
                source_ref=source_ref,
                metadata=metadata,
            )
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to register asset file for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to register asset file for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def register_asset_file_record(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
    title: str = "",
    mime_type: str | None = None,
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> None:
    _register_asset_file_best_effort(
        project_name,
        file,
        asset_type=asset_type,
        logical_key=logical_key,
        story_id=story_id,
        title=title,
        mime_type=mime_type,
        source_kind=source_kind,
        source_ref=source_ref,
        metadata=metadata,
    )


def _sync_asset_payload_to_db_best_effort(
    project_name: str,
    file: Path,
    *,
    asset_type: str,
    logical_key: str,
    payload,
    story_id: str | None = None,
    title: str = "",
    mime_type: str = "application/json",
    source_kind: str | None = None,
    source_ref: str | None = None,
    metadata: dict | None = None,
) -> str | None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        root = project_path(project_name).resolve()
        resolved_file = file.resolve()
        relative_path = str(resolved_file.relative_to(root)).replace("\\", "/")
        content_hash = ""
        if resolved_file.exists() and resolved_file.is_file():
            content_hash = hashlib.sha256(resolved_file.read_bytes()).hexdigest()
        asset_id_source = f"{story_id or 'project'}:{asset_type}:{logical_key}"
        asset_id = "asset_" + hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
        with open_project_db(root) as conn:
            asset_record = register_asset_file(
                conn,
                asset_id=asset_id,
                story_id=story_id,
                asset_type=asset_type,
                logical_key=logical_key,
                title=title,
                relative_path=relative_path,
                content_hash=content_hash or None,
                mime_type=mime_type,
                source_kind=source_kind,
                source_ref=source_ref,
                metadata=metadata,
            )
            actual_asset_id = str(asset_record.get("asset_id") or asset_id)
            upsert_asset_payload(
                conn,
                asset_type=asset_type,
                logical_key=logical_key,
                story_id=story_id,
                payload=payload,
            )
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync asset payload to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync asset payload to project database for {project_name}.", exc)
        return None
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))
        return actual_asset_id


def _load_asset_payload_from_db_best_effort(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
):
    if _project_db_marked_unavailable(project_name):
        return None
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return load_asset_payload(
                conn,
                asset_type=asset_type,
                logical_key=logical_key,
                story_id=story_id,
            )
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load asset payload from project database for %s/%s/%s: %s",
            project_name,
            asset_type,
            logical_key,
            exc,
        )
        _raise_if_db_only(f"Failed to load asset payload from project database for {project_name}.", exc)
        return None


def list_asset_records(
    project_name: str,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    if _project_db_marked_unavailable(project_name):
        return []
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return list_asset_file_rows(
                conn,
                asset_type=asset_type,
                story_id=story_id,
                include_deleted=include_deleted,
            )
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to list asset records for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to list asset records for {project_name}.", exc)
        return []


def list_asset_payload_records(
    project_name: str,
    *,
    asset_type: str | None = None,
    story_id: str | None = None,
    include_deleted: bool = False,
) -> list[dict]:
    if _project_db_marked_unavailable(project_name):
        return []
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return list_asset_payload_rows(
                conn,
                asset_type=asset_type,
                story_id=story_id,
                include_deleted=include_deleted,
            )
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to list asset payload records for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to list asset payload records for {project_name}.", exc)
        return []


def _asset_payload_exists(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> bool:
    for record in list_asset_payload_records(project_name, asset_type=asset_type, story_id=story_id):
        if str(record.get("logical_key") or "") == logical_key:
            return True
    return False


CONTEXT_DIRECTIVE_ASSET_TYPE = "context_directive"
GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE = "generation_context_snapshot"


def _validate_context_asset_key(value: str, label: str) -> str:
    normalized = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,96}", normalized):
        raise ValueError(f"{label} 只能包含字母、数字、下划线和连字符，且长度不能超过 96。")
    return normalized


def _context_directive_record_story_id(scope: str, story_id: str | None) -> str | None:
    if str(scope or "").strip().lower() == "project":
        return None
    return _memory_api.normalize_story_id(str(story_id or "default"))


def _context_asset_path(
    project_name: str,
    asset_type: str,
    logical_key: str,
    story_id: str | None,
) -> Path:
    if story_id is None:
        return project_path(project_name) / asset_type / f"{logical_key}.json"
    return _memory_api.story_path(project_name, story_id) / asset_type / f"{logical_key}.json"


def save_context_directive(
    project_name: str,
    directive: dict,
    *,
    story_id: str | None = None,
) -> dict:
    raw = dict(directive or {})
    directive_id = _validate_context_asset_key(
        str(raw.get("directive_id") or f"directive_{uuid4().hex}"),
        "导演注 ID",
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw["directive_id"] = directive_id
    raw["created_at"] = str(raw.get("created_at") or now)
    raw["updated_at"] = now
    normalized = ContextDirective.model_validate(raw).model_dump()
    normalized["content"] = str(normalized.get("content") or "").strip()
    normalized["name"] = str(normalized.get("name") or "").strip()
    if not normalized["content"]:
        raise ValueError("导演注内容不能为空。")
    if not normalized["name"]:
        normalized["name"] = str(normalized["content"]).splitlines()[0][:48] or "未命名导演注"

    record_story_id = _context_directive_record_story_id(normalized["scope"], story_id or normalized.get("story_id"))
    normalized["story_id"] = record_story_id
    path = _context_asset_path(
        project_name,
        CONTEXT_DIRECTIVE_ASSET_TYPE,
        directive_id,
        record_story_id,
    )
    asset_id = _sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE,
        logical_key=directive_id,
        story_id=record_story_id,
        title=str(normalized.get("name") or "导演注"),
        payload=normalized,
        source_kind="internal",
        metadata={
            "scope": normalized["scope"],
            "placement": normalized["placement"],
            "capabilities": normalized["capabilities"],
        },
    )
    if not asset_id:
        raise RuntimeError("导演注未能写入项目数据库。")
    return normalized


def load_context_directives(project_name: str, story_id: str = "default") -> list[dict]:
    target_story_id = _memory_api.normalize_story_id(story_id)
    directives: list[dict] = []
    records = list_asset_payload_records(project_name, asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE)
    for record in records:
        record_story_id = str(record.get("story_id") or "").strip() or None
        if record_story_id not in {None, target_story_id}:
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            continue
        try:
            directive = ContextDirective.model_validate(payload).model_dump()
        except Exception as exc:
            logging.getLogger("novelforge.storage").warning(
                "Skipping invalid context directive %s: %s",
                record.get("logical_key"),
                exc,
            )
            continue
        if (directive["scope"] == "project") != (record_story_id is None):
            logging.getLogger("novelforge.storage").warning(
                "Skipping context directive with mismatched scope and owner: %s",
                record.get("logical_key"),
            )
            continue
        directive["story_id"] = record_story_id
        directives.append(directive)
    directives.sort(
        key=lambda item: (
            0 if item.get("scope") == "project" else 1,
            -int(item.get("priority") or 0),
            str(item.get("updated_at") or ""),
            str(item.get("directive_id") or ""),
        )
    )
    return directives


def _directive_not_expired(expires_at: str | None, now: datetime) -> bool:
    text = str(expires_at or "").strip()
    if not text:
        return True
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed > now
    except ValueError:
        return False


def load_effective_context_directives(
    project_name: str,
    story_id: str = "default",
    *,
    capability: str = "",
    chapter_no: int | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc)
    normalized_capability = str(capability or "").strip()
    effective: list[dict] = []
    for directive in load_context_directives(project_name, story_id):
        if not directive.get("enabled", True):
            continue
        remaining_uses = directive.get("remaining_uses")
        if remaining_uses is not None and int(remaining_uses) <= 0:
            continue
        if not _directive_not_expired(directive.get("expires_at"), now):
            continue
        capabilities = [str(value).strip() for value in directive.get("capabilities", []) if str(value).strip()]
        if capabilities and normalized_capability and normalized_capability not in capabilities:
            continue
        scope = str(directive.get("scope") or "story")
        if scope == "chapter":
            if chapter_no is None:
                continue
            start = directive.get("chapter_start")
            end = directive.get("chapter_end")
            if start is not None and chapter_no < int(start):
                continue
            if end is not None and chapter_no > int(end):
                continue
        effective.append(directive)
    return effective


def delete_context_directive(
    project_name: str,
    directive_id: str,
    *,
    story_id: str = "default",
) -> bool:
    target_id = str(directive_id or "").strip()
    if not target_id:
        return False
    for directive in load_context_directives(project_name, story_id):
        if str(directive.get("directive_id") or "") != target_id:
            continue
        record_story_id = directive.get("story_id")
        _mark_asset_deleted_best_effort(
            project_name,
            asset_type=CONTEXT_DIRECTIVE_ASSET_TYPE,
            logical_key=target_id,
            story_id=record_story_id,
        )
        return True
    return False


def consume_context_directives(
    project_name: str,
    story_id: str,
    directive_ids: list[str],
) -> list[dict]:
    target_ids = {str(value or "").strip() for value in directive_ids if str(value or "").strip()}
    if not target_ids:
        return []
    consumed: list[dict] = []
    for directive in load_context_directives(project_name, story_id):
        if str(directive.get("directive_id") or "") not in target_ids:
            continue
        remaining_uses = directive.get("remaining_uses")
        if remaining_uses is None or int(remaining_uses) <= 0:
            continue
        updated = dict(directive)
        updated["remaining_uses"] = max(int(remaining_uses) - 1, 0)
        if updated["remaining_uses"] == 0:
            updated["enabled"] = False
        consumed.append(save_context_directive(
            project_name,
            updated,
            story_id=directive.get("story_id"),
        ))
    return consumed


def save_generation_context_snapshot(
    project_name: str,
    story_id: str,
    payload: dict,
) -> str:
    normalized_story_id = _memory_api.normalize_story_id(story_id)
    snapshot = dict(payload or {})
    fingerprint = str(snapshot.get("fingerprint") or "").strip()
    assembly_id = _validate_context_asset_key(
        str(snapshot.get("assembly_id") or f"assembly_{uuid4().hex}"),
        "上下文装配 ID",
    )
    logical_key = f"{assembly_id}_{fingerprint[:12]}" if fingerprint else assembly_id
    path = _context_asset_path(
        project_name,
        GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        logical_key,
        normalized_story_id,
    )
    asset_id = _sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type=GENERATION_CONTEXT_SNAPSHOT_ASSET_TYPE,
        logical_key=logical_key,
        story_id=normalized_story_id,
        title=f"生成上下文 {snapshot.get('capability') or ''} {snapshot.get('chapter_no') or ''}".strip(),
        payload=snapshot,
        source_kind="generation",
        source_ref=fingerprint or None,
        metadata={
            "capability": snapshot.get("capability"),
            "chapter_no": snapshot.get("chapter_no"),
            "fingerprint": fingerprint,
        },
    )
    if not asset_id:
        raise RuntimeError("生成上下文快照未能写入项目数据库。")
    return logical_key


def sync_retrieval_source_file_record(
    project_name: str,
    *,
    relative_path: str,
    title: str,
    content_hash: str | None = None,
    source_type: str = "reference",
    authority: float = 0.0,
    metadata: dict | None = None,
) -> dict:
    result = _sync_source_to_db_best_effort(
        project_name,
        lambda conn: sync_retrieval_source_file(
            conn,
            relative_path=relative_path,
            title=title,
            content_hash=content_hash,
            source_type=source_type,
            authority=authority,
            metadata=metadata,
        ),
    )
    return dict(result or {})


def _mark_asset_deleted_best_effort(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            mark_asset_deleted(
                conn,
                asset_type=asset_type,
                logical_key=logical_key,
                story_id=story_id,
            )
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to mark asset deleted for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to mark asset deleted for {project_name}.", exc)


def mark_asset_deleted_record(
    project_name: str,
    *,
    asset_type: str,
    logical_key: str,
    story_id: str | None = None,
) -> None:
    _mark_asset_deleted_best_effort(
        project_name,
        asset_type=asset_type,
        logical_key=logical_key,
        story_id=story_id,
    )


def _sync_knowledge_category_to_db_best_effort(project_name: str, category: str, items: list[dict]) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            sync_knowledge_category(conn, category, items)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync knowledge category to project database for %s/%s: %s",
            project_name,
            category,
            exc,
        )
        _raise_if_db_only(f"Failed to sync knowledge category to project database for {project_name}/{category}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def _sync_pending_knowledge_to_db_best_effort(project_name: str, items: list[dict]) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            sync_pending_knowledge(conn, items)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync pending knowledge to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync pending knowledge to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def _sync_entity_aliases_to_db_best_effort(project_name: str, items: list[dict]) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            sync_entity_alias_groups(conn, items)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync entity aliases to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync entity aliases to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def _load_knowledge_category_from_db_best_effort(project_name: str, category: str) -> list[dict] | None:
    if _project_db_marked_unavailable(project_name):
        return None
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return load_knowledge_category_rows(conn, category)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load knowledge category from project database for %s/%s: %s",
            project_name,
            category,
            exc,
        )
        _raise_if_db_only(f"Failed to load knowledge category from project database for {project_name}/{category}.", exc)
        return None


def _load_pending_knowledge_from_db_best_effort(project_name: str) -> list[dict] | None:
    if _project_db_marked_unavailable(project_name):
        return None
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return load_pending_knowledge_rows(conn)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load pending knowledge from project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to load pending knowledge from project database for {project_name}.", exc)
        return None


def _load_entity_aliases_from_db_best_effort(project_name: str) -> list[dict] | None:
    if _project_db_marked_unavailable(project_name):
        return None
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            return load_entity_alias_group_rows(conn)
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to load entity aliases from project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to load entity aliases from project database for {project_name}.", exc)
        return None


def _sync_source_to_db_best_effort(project_name: str, callback):
    if _project_db_marked_unavailable(project_name):
        return None
    result = None
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            result = callback(conn)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync source record to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync source record to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))
    return result


def _sync_retrieval_to_db_best_effort(project_name: str, callback) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            callback(conn)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync retrieval index to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync retrieval index to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def _sync_workflow_to_db_best_effort(project_name: str, callback) -> None:
    if _project_db_marked_unavailable(project_name):
        return
    try:
        with open_project_db(project_path(project_name).resolve()) as conn:
            callback(conn)
            conn.commit()
    except Exception as exc:
        _DB_UNAVAILABLE_PROJECTS.add(project_name)
        logging.getLogger("novelforge.storage").warning(
            "Failed to sync workflow run to project database for %s: %s",
            project_name,
            exc,
        )
        _raise_if_db_only(f"Failed to sync workflow run to project database for {project_name}.", exc)
    else:
        _delete_pending_mirrors(_take_project_pending_mirror_deletions(project_name))


def create_project(project_name: str) -> str:
    normalized_name = normalize_project_name(project_name)
    if project_is_discoverable(normalized_name):
        raise FileExistsError("Project already exists.")
    if project_data_exists(normalized_name):
        raise FileExistsError("Project data directory already exists but is not recognized as a project.")

    ensure_project_path(normalized_name)
    _initialize_project_db_best_effort(normalized_name)
    _memory_api.load_stories_index(normalized_name)
    load_memory(normalized_name)
    _memory_api.load_creative_profile(normalized_name)
    _memory_api.load_project_rules(normalized_name)
    _memory_api.knowledge_dir_path(normalized_name)
    _memory_api.save_pending_knowledge_items(normalized_name, _memory_api.load_pending_knowledge_items(normalized_name))
    _memory_api.long_reference_batches_path(normalized_name)
    _memory_api.retrieval_sources_path(normalized_name)
    register_project(normalized_name, make_active=True)
    return normalized_name


def normalize_memory(project_name: str, memory: dict | None) -> dict:
    normalized = DEFAULT_MEMORY.copy()
    if isinstance(memory, dict):
        normalized.update(memory)

    normalized["title"] = normalized.get("title") or project_name

    for key in ["au_rules", "world", "characters", "relationships", "timeline", "foreshadowing", "active_constraints", "chapter_summaries", "locations", "organizations", "power_systems", "relationship_graph"]:
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    genre = normalized.get("genre", "")
    normalized["genre"] = genre if isinstance(genre, str) else str(genre)
    canon_mode = normalized.get("canon_mode", "")
    normalized["canon_mode"] = canon_mode if isinstance(canon_mode, str) else str(canon_mode)
    return normalized


def slim_memory_for_storage(project_name: str, memory: dict | None) -> dict:
    normalized = normalize_memory(project_name, memory)
    return {
        "title": normalized.get("title") or project_name,
        "genre": normalized.get("genre", ""),
    }


def sync_project_retrieval_assets(project_name: str):
    try:
        from novelforge.services.retrieval import rebuild_retrieval_assets

        rebuild_retrieval_assets(project_name, build_vectors=False)
    except Exception as exc:
        import logging

        logging.getLogger("novelforge").warning(
            "Failed to sync retrieval assets for project %s: %s",
            project_name, exc,
        )


def load_memory(project_name: str) -> dict:
    db_meta = _load_runtime_from_db_best_effort(
        project_name,
        lambda conn: get_project_meta(conn, project_name) or {},
        "project metadata",
    )
    if db_meta is not None:
        return normalize_memory(project_name, {
            "title": db_meta.get("title") or project_name,
            "genre": db_meta.get("genre") or "",
        })
    path = project_path(project_name) / "memory.json"

    if not path.exists():
        memory = normalize_memory(project_name, None)
        save_memory(project_name, slim_memory_for_storage(project_name, memory))
        return memory

    try:
        memory = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        memory = normalize_memory(project_name, None)
        save_memory(project_name, slim_memory_for_storage(project_name, memory))
        return memory
    return normalize_memory(project_name, memory)


def save_memory(project_name: str, memory: dict):
    path = project_path(project_name) / "memory.json"
    normalized = slim_memory_for_storage(project_name, memory)
    _write_json_mirror(path, normalized)
    _sync_runtime_to_db_best_effort(
        project_name,
        lambda conn: upsert_project_meta(
            conn,
            project_name=project_name,
            title=normalized.get("title") or project_name,
            genre=normalized.get("genre") or "",
        ),
    )
    sync_project_retrieval_assets(project_name)
