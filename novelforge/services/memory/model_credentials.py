"""Transactional persistence for reference-backed model credentials."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from novelforge.services.credentials import (
    delete_system_credential,
    hydrate_llm_profiles_payload,
    scrub_legacy_model_environment_secrets,
    secure_llm_profiles_payload,
)
from storage import open_global_db
from storage.repositories import sync_global_setting


def persist_llm_profiles_payload(
    payload: dict,
    *,
    normalize: Callable[[dict], dict],
    global_db_unavailable: Callable[[], bool],
    write_json_mirror: Callable[[Path, object], None],
    profiles_path: Path,
    env_path: Path,
    data_path: Path = Path("data"),
) -> dict:
    """Commit profile references atomically, then retire superseded secrets."""

    normalized = normalize(payload)
    secured = secure_llm_profiles_payload(normalized)
    old_refs = _credential_refs(normalized)
    new_refs = _credential_refs(secured)
    if global_db_unavailable():
        _remove_credentials(new_refs - old_refs)
        raise RuntimeError("系统凭据已保存，但全局数据库不可用，模型方案未写入。")
    try:
        with open_global_db(data_path) as conn:
            sync_global_setting(conn, "llm_profiles", secured)
            conn.commit()
    except Exception as exc:
        _remove_credentials(new_refs - old_refs)
        raise RuntimeError("全局数据库写入失败，未清理旧密钥来源。") from exc
    _remove_credentials(old_refs - new_refs, warn=True)
    try:
        write_json_mirror(profiles_path, secured)
    except OSError as exc:
        logging.getLogger("novelforge.storage").warning(
            "Model profiles were saved to SQLite, but the compatibility mirror failed: %s",
            exc,
        )
    scrub_legacy_model_secrets_safely(env_path)
    return secured


def hydrate_llm_profiles_safely(payload: dict, normalize: Callable[[dict], dict]) -> dict:
    try:
        return hydrate_llm_profiles_payload(payload, normalize)
    except Exception as exc:
        logging.getLogger("novelforge.credentials").warning(
            "Failed to hydrate model credentials: %s", exc
        )
        return normalize(payload)


def scrub_legacy_model_secrets_safely(env_path: Path) -> None:
    try:
        scrub_legacy_model_environment_secrets(env_path)
    except Exception as exc:
        logging.getLogger("novelforge.credentials").warning(
            "Legacy model credential cleanup will be retried: %s", exc
        )


def _credential_refs(payload: dict) -> set[str]:
    return {
        str(profile.get(field) or "")
        for profile in payload.get("profiles", [])
        for field in ("api_key_ref", "embedding_api_key_ref")
        if str(profile.get(field) or "")
    }


def _remove_credentials(credential_refs: set[str], *, warn: bool = False) -> None:
    for credential_ref in credential_refs:
        try:
            delete_system_credential(credential_ref)
        except Exception as exc:
            if warn:
                logging.getLogger("novelforge.credentials").warning(
                    "Failed to remove superseded credential %s: %s",
                    credential_ref,
                    exc,
                )
