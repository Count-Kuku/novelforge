"""Global LLM profile persistence: normalization, credentials migration and env sync."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dotenv import dotenv_values

from novelforge.core.cost_currency import cost_display_preferences

from .db_availability import (
    _global_db_marked_unavailable,
    _load_global_from_db_best_effort,
)
from .paths import ENV_PATH, LLM_PROFILES_PATH
from storage.repositories import load_global_setting

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
    normalized = {
        # Secrets live in the system credential manager.  Blank legacy entries
        # also scrub keys left behind by older releases.
        "LLM_API_KEY": "",
        "DEEPSEEK_API_KEY": "",
        "LLM_BASE_URL": str(settings.get("base_url", "") or ""),
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
