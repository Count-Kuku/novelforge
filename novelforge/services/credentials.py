"""System credential storage with reference-only SQLite metadata.

Secrets are written to Windows Credential Manager or the optional system
``keyring`` backend.  The in-memory backend is deliberately opt-in and exists
only for isolated tests.
"""

from __future__ import annotations

import ctypes
import hashlib
import os
import re
from ctypes import wintypes
from pathlib import Path
from threading import RLock
from uuid import uuid4

from storage import initialize_global_db, open_global_db
from storage.repositories import (
    load_credential_reference_row,
    mark_credential_reference_deleted_row,
    upsert_credential_reference_row,
)


SERVICE_NAME = "NovelForge"
_MEMORY_SECRETS: dict[str, str] = {}
_MEMORY_LOCK = RLock()


class CredentialStoreUnavailable(RuntimeError):
    """Raised when no supported system credential manager is available."""


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", wintypes.LPVOID),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _target_name(credential_ref: str) -> str:
    return f"{SERVICE_NAME}/{credential_ref}"


def _selected_backend() -> str:
    requested = str(os.getenv("NOVELFORGE_CREDENTIAL_BACKEND") or "auto").strip().lower()
    if requested == "memory":
        return "memory"
    if requested not in {"auto", "windows", "keyring"}:
        raise CredentialStoreUnavailable(f"不支持的凭据后端：{requested}")
    if requested == "windows" or (requested == "auto" and os.name == "nt"):
        return "windows"
    try:
        import keyring  # noqa: F401
    except ImportError as exc:
        raise CredentialStoreUnavailable(
            "当前系统没有可用的凭据管理器；请安装 keyring，或在测试中显式使用 memory 后端。"
        ) from exc
    return "keyring"


def _windows_write(target: str, secret: str) -> None:
    blob = secret.encode("utf-8")
    buffer = (ctypes.c_ubyte * max(len(blob), 1))()
    if blob:
        ctypes.memmove(buffer, blob, len(blob))
    credential = _CREDENTIALW()
    credential.Type = 1  # CRED_TYPE_GENERIC
    credential.TargetName = target
    credential.CredentialBlobSize = len(blob)
    credential.CredentialBlob = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte))
    credential.Persist = 2  # CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = SERVICE_NAME
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    advapi32.CredWriteW.restype = wintypes.BOOL
    if not advapi32.CredWriteW(ctypes.byref(credential), 0):
        raise ctypes.WinError(ctypes.get_last_error())


def _windows_read(target: str) -> str:
    pointer = ctypes.POINTER(_CREDENTIALW)()
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredReadW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    advapi32.CredReadW.restype = wintypes.BOOL
    advapi32.CredFree.argtypes = [wintypes.LPVOID]
    if not advapi32.CredReadW(target, 1, 0, ctypes.byref(pointer)):
        error = ctypes.get_last_error()
        if error == 1168:  # ERROR_NOT_FOUND
            return ""
        raise ctypes.WinError(error)
    try:
        credential = pointer.contents
        raw = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return raw.decode("utf-8")
    finally:
        advapi32.CredFree(pointer)


def _windows_delete(target: str) -> None:
    advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
    advapi32.CredDeleteW.restype = wintypes.BOOL
    if not advapi32.CredDeleteW(target, 1, 0):
        error = ctypes.get_last_error()
        if error != 1168:
            raise ctypes.WinError(error)


def _write_secret(backend: str, credential_ref: str, secret: str) -> None:
    target = _target_name(credential_ref)
    if backend == "windows":
        _windows_write(target, secret)
    elif backend == "keyring":
        import keyring

        keyring.set_password(SERVICE_NAME, credential_ref, secret)
    elif backend == "memory":
        with _MEMORY_LOCK:
            _MEMORY_SECRETS[credential_ref] = secret
    else:  # pragma: no cover - defensive guard
        raise CredentialStoreUnavailable(f"不支持的凭据后端：{backend}")


def _read_secret(backend: str, credential_ref: str) -> str:
    if backend == "windows":
        return _windows_read(_target_name(credential_ref))
    if backend == "keyring":
        import keyring

        return str(keyring.get_password(SERVICE_NAME, credential_ref) or "")
    if backend == "memory":
        with _MEMORY_LOCK:
            return _MEMORY_SECRETS.get(credential_ref, "")
    return ""


def _delete_secret(backend: str, credential_ref: str) -> None:
    if backend == "windows":
        _windows_delete(_target_name(credential_ref))
    elif backend == "keyring":
        import keyring
        from keyring.errors import PasswordDeleteError

        try:
            keyring.delete_password(SERVICE_NAME, credential_ref)
        except PasswordDeleteError:
            pass
    elif backend == "memory":
        with _MEMORY_LOCK:
            _MEMORY_SECRETS.pop(credential_ref, None)


def build_credential_ref(purpose: str, owner_id: str) -> str:
    safe_purpose = "".join(char if char.isalnum() or char in "._-" else "-" for char in purpose)
    safe_owner = "".join(char if char.isalnum() or char in "._-" else "-" for char in owner_id)
    return f"novelforge:{safe_purpose}:{safe_owner}" if safe_owner else f"novelforge:{safe_purpose}:{uuid4().hex}"


def store_system_credential(
    secret: str,
    *,
    purpose: str,
    owner_id: str = "",
    credential_ref: str = "",
    data_path: Path = Path("data"),
) -> dict:
    value = str(secret or "")
    if not value:
        raise ValueError("不能保存空凭据。")
    reference = str(credential_ref or build_credential_ref(purpose, owner_id)).strip()
    backend = _selected_backend()
    _write_secret(backend, reference, value)
    metadata = {
        "credential_ref": reference,
        "purpose": str(purpose or "").strip(),
        "owner_id": str(owner_id or "").strip(),
        "backend": backend,
        "fingerprint": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "last_four": value[-4:],
        "metadata": {"service": SERVICE_NAME},
    }
    try:
        initialize_global_db(data_path)
        with open_global_db(data_path) as conn:
            return upsert_credential_reference_row(conn, metadata)
    except Exception:
        _delete_secret(backend, reference)
        raise


def load_credential_metadata(credential_ref: str, *, data_path: Path = Path("data")) -> dict:
    if not str(credential_ref or "").strip():
        return {}
    initialize_global_db(data_path)
    with open_global_db(data_path) as conn:
        return load_credential_reference_row(conn, credential_ref)


def resolve_system_credential(credential_ref: str, *, data_path: Path = Path("data")) -> str:
    metadata = load_credential_metadata(credential_ref, data_path=data_path)
    if not metadata:
        return ""
    return _read_secret(str(metadata.get("backend") or ""), str(credential_ref or ""))


def delete_system_credential(credential_ref: str, *, data_path: Path = Path("data")) -> bool:
    metadata = load_credential_metadata(credential_ref, data_path=data_path)
    if not metadata:
        return False
    _delete_secret(str(metadata.get("backend") or ""), credential_ref)
    with open_global_db(data_path) as conn:
        return mark_credential_reference_deleted_row(conn, credential_ref)


def _dotenv_secret(path: Path, key: str) -> str:
    if not path.is_file():
        return ""
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(.*?)\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'\"', "'"}:
            value = value[1:-1]
        return value
    return ""


def _scrub_dotenv_secret(path: Path, key: str) -> None:
    if not path.is_file():
        return
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    lines = path.read_text(encoding="utf-8").splitlines()
    updated = [f"{key}=" if pattern.match(line) else line for line in lines]
    path.write_text("\n".join(updated).rstrip() + "\n", encoding="utf-8")


def resolve_or_migrate_environment_credential(
    *,
    purpose: str,
    owner_id: str,
    environment_key: str,
    dotenv_path: Path = Path(".env"),
    data_path: Path = Path("data"),
) -> str:
    """Resolve a named credential, importing and scrubbing a legacy env value."""

    credential_ref = build_credential_ref(purpose, owner_id)
    existing = resolve_system_credential(credential_ref, data_path=data_path)
    if existing:
        return existing
    legacy = str(os.getenv(environment_key) or _dotenv_secret(dotenv_path, environment_key)).strip()
    if not legacy:
        return ""
    store_system_credential(
        legacy,
        purpose=purpose,
        owner_id=owner_id,
        credential_ref=credential_ref,
        data_path=data_path,
    )
    os.environ.pop(environment_key, None)
    _scrub_dotenv_secret(dotenv_path, environment_key)
    return legacy


def system_credential_available(
    *, purpose: str, owner_id: str, data_path: Path = Path("data")
) -> bool:
    credential_ref = build_credential_ref(purpose, owner_id)
    try:
        return bool(resolve_system_credential(credential_ref, data_path=data_path))
    except Exception:
        return False


def scrub_legacy_model_environment_secrets(dotenv_path: Path = Path(".env")) -> None:
    for key in (
        "LLM_API_KEY",
        "DEEPSEEK_API_KEY",
        "LLM_EMBEDDING_API_KEY",
    ):
        os.environ.pop(key, None)
        _scrub_dotenv_secret(dotenv_path, key)


def secure_llm_profiles_payload(payload: dict) -> dict:
    """Replace raw model keys with system-credential references."""

    secured = {
        "active_profile_id": str(payload.get("active_profile_id") or ""),
        "profiles": [],
    }
    for source_profile in payload.get("profiles", []):
        profile = dict(source_profile or {})
        profile_id = str(profile.get("id") or "default")
        for secret_field, purpose in (
            ("api_key", "llm-chat"),
            ("embedding_api_key", "llm-embedding"),
        ):
            secret = str(profile.pop(secret_field, "") or "").strip()
            credential_ref = str(profile.get(f"{secret_field}_ref") or "").strip()
            if secret:
                metadata = store_system_credential(
                    secret,
                    purpose=purpose,
                    owner_id=profile_id,
                    credential_ref=credential_ref,
                )
                for suffix, metadata_field in (
                    ("ref", "credential_ref"),
                    ("fingerprint", "fingerprint"),
                    ("last_four", "last_four"),
                    ("backend", "backend"),
                ):
                    profile[f"{secret_field}_{suffix}"] = metadata[metadata_field]
            elif not credential_ref:
                for suffix in ("ref", "fingerprint", "last_four", "backend"):
                    profile.pop(f"{secret_field}_{suffix}", None)
        secured["profiles"].append(profile)
    return secured


def hydrate_llm_profiles_payload(payload: dict, normalize) -> dict:
    """Resolve reference-backed model keys for runtime use only."""

    hydrated = normalize(payload)
    for profile in hydrated.get("profiles", []):
        for secret_field in ("api_key", "embedding_api_key"):
            if str(profile.get(secret_field) or ""):
                continue
            credential_ref = str(profile.get(f"{secret_field}_ref") or "").strip()
            if credential_ref:
                profile[secret_field] = resolve_system_credential(credential_ref)
    return hydrated
