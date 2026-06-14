import json
import os
import re
from pathlib import Path

from dotenv import dotenv_values

from schemas import ArcOutlineMetadata, ChapterOutlineMetadata, VolumeOutlineMetadata

BASE_DIR = Path("data/projects")
GLOBAL_RULES_PATH = Path("data/global_rules.json")
ENV_PATH = Path(".env")
LLM_PROFILES_PATH = Path("data/llm_profiles.json")
RULE_SCOPES = ["all", "outline", "chapter_outline", "write", "review", "memory_update"]
DEFAULT_LLM_BASE_URL = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-flash"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
MANAGED_ENV_KEYS = [
    "LLM_API_KEY",
    "DEEPSEEK_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "LLM_EMBEDDING_MODEL",
]
DEFAULT_LLM_PROFILE_NAME = "默认配置"
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
    "chapter_summaries": []
}


def _default_rules() -> dict:
    return {
        "all": [],
        "outline": [],
        "chapter_outline": [],
        "write": [],
        "review": [],
        "memory_update": [],
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
    return {
        "id": profile_id,
        "name": name,
        "base_url": str(raw.get("base_url") or DEFAULT_LLM_BASE_URL),
        "api_key": str(raw.get("api_key") or ""),
        "model_name": str(raw.get("model_name") or DEFAULT_LLM_MODEL),
        "embedding_model_name": str(raw.get("embedding_model_name") or DEFAULT_EMBEDDING_MODEL),
    }


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
        or DEFAULT_EMBEDDING_MODEL
    )
    return _normalize_llm_profile(
        {
            "id": "default",
            "name": DEFAULT_LLM_PROFILE_NAME,
            "base_url": base_url,
            "api_key": api_key,
            "model_name": model_name,
            "embedding_model_name": embedding_model_name,
        },
        "default",
    )


def load_llm_profiles() -> dict:
    LLM_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LLM_PROFILES_PATH.exists():
        env_profile = _load_env_llm_profile()
        payload = {
            "active_profile_id": env_profile["id"],
            "profiles": [env_profile],
        }
        save_llm_profiles(payload)
        return payload

    try:
        raw_payload = json.loads(LLM_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        raw_payload = _default_llm_profile_payload()

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
        env_profile = _load_env_llm_profile()
        normalized_profiles = [env_profile]

    active_profile_id = str((raw_payload.get("active_profile_id") if isinstance(raw_payload, dict) else "") or "").strip()
    if active_profile_id not in {profile["id"] for profile in normalized_profiles}:
        active_profile_id = normalized_profiles[0]["id"]

    payload = {
        "active_profile_id": active_profile_id,
        "profiles": normalized_profiles,
    }
    if payload != raw_payload:
        save_llm_profiles(payload)
    return payload


def save_llm_profiles(payload: dict):
    LLM_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw_profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
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

    active_profile_id = str(payload.get("active_profile_id") or "").strip()
    if active_profile_id not in {profile["id"] for profile in normalized_profiles}:
        active_profile_id = normalized_profiles[0]["id"]

    normalized_payload = {
        "active_profile_id": active_profile_id,
        "profiles": normalized_profiles,
    }
    LLM_PROFILES_PATH.write_text(json.dumps(normalized_payload, ensure_ascii=False, indent=2), encoding="utf-8")


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
        "base_url": str(active_profile.get("base_url") or DEFAULT_LLM_BASE_URL),
        "model_name": str(active_profile.get("model_name") or DEFAULT_LLM_MODEL),
        "embedding_model_name": str(active_profile.get("embedding_model_name") or DEFAULT_EMBEDDING_MODEL),
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
        "LLM_API_KEY": str(settings.get("api_key", "") or ""),
        "DEEPSEEK_API_KEY": str(settings.get("api_key", "") or ""),
        "LLM_BASE_URL": str(settings.get("base_url", "") or ""),
        "LLM_MODEL": str(settings.get("model_name", "") or ""),
        "LLM_EMBEDDING_MODEL": str(settings.get("embedding_model_name", "") or ""),
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
    normalized = _normalize_llm_profile(profile, target_id or f"profile_{len(payload.get('profiles', [])) + 1:03d}")

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
    remaining_profiles = [profile for profile in payload.get("profiles", []) if profile.get("id") != target_id]
    if len(remaining_profiles) == len(payload.get("profiles", [])):
        raise ValueError("LLM profile not found.")
    if not remaining_profiles:
        raise ValueError("At least one LLM profile must remain.")

    payload["profiles"] = remaining_profiles
    if payload.get("active_profile_id") == target_id:
        payload["active_profile_id"] = remaining_profiles[0]["id"]
    save_llm_profiles(payload)
    active_profile = get_active_llm_profile()
    save_llm_settings(active_profile)
    return payload


def project_path(project_name: str) -> Path:
    path = BASE_DIR / project_name.strip()
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_project(project_name: str) -> str:
    normalized_name = project_name.strip()
    if not normalized_name:
        raise ValueError("Project name cannot be empty.")

    project_path(normalized_name)
    load_memory(normalized_name)
    load_project_rules(normalized_name)
    retrieval_sources_path(normalized_name)
    return normalized_name


def list_projects() -> list[str]:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    return sorted(
        [path.name for path in BASE_DIR.iterdir() if path.is_dir()],
        key=str.lower
    )


def normalize_memory(project_name: str, memory: dict | None) -> dict:
    normalized = DEFAULT_MEMORY.copy()
    if isinstance(memory, dict):
        normalized.update(memory)

    normalized["title"] = normalized.get("title") or project_name

    for key in ["au_rules", "world", "characters", "relationships", "timeline", "foreshadowing", "active_constraints", "chapter_summaries"]:
        value = normalized.get(key)
        normalized[key] = value if isinstance(value, list) else []

    genre = normalized.get("genre", "")
    normalized["genre"] = genre if isinstance(genre, str) else str(genre)
    canon_mode = normalized.get("canon_mode", "")
    normalized["canon_mode"] = canon_mode if isinstance(canon_mode, str) else str(canon_mode)
    return normalized


def sync_project_retrieval_assets(project_name: str):
    try:
        from retrieval import rebuild_retrieval_assets

        rebuild_retrieval_assets(project_name, build_vectors=False)
    except Exception:
        pass


def load_memory(project_name: str) -> dict:
    path = project_path(project_name) / "memory.json"

    if not path.exists():
        memory = normalize_memory(project_name, None)
        save_memory(project_name, memory)
        return memory

    memory = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_memory(project_name, memory)

    if normalized != memory:
        save_memory(project_name, normalized)

    return normalized


def save_memory(project_name: str, memory: dict):
    path = project_path(project_name) / "memory.json"
    normalized = normalize_memory(project_name, memory)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    sync_project_retrieval_assets(project_name)


def load_global_rules() -> dict:
    GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_RULES_PATH.exists():
        rules = normalize_rules(None)
        save_global_rules(rules)
        return rules

    rules = json.loads(GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
    normalized = normalize_rules(rules)
    if normalized != rules:
        save_global_rules(normalized)
    return normalized


def save_global_rules(rules: dict):
    GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_rules(rules)
    GLOBAL_RULES_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_project_rules(project_name: str) -> dict:
    path = project_path(project_name) / "rules.json"
    if not path.exists():
        rules = normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules

    rules = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize_rules(rules)
    if normalized != rules:
        save_project_rules(project_name, normalized)
    return normalized


def save_project_rules(project_name: str, rules: dict):
    path = project_path(project_name) / "rules.json"
    normalized = normalize_rules(rules)
    path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def save_outline(project_name: str, outline: str):
    path = project_path(project_name) / "outline.md"
    path.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_outline(project_name: str) -> str:
    path = project_path(project_name) / "outline.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _outline_discussion_path(project_name: str) -> Path:
    return project_path(project_name) / "outline.discussion.json"


def save_outline_discussion_artifact(project_name: str, discussion: dict, report_markdown: str):
    path = _outline_discussion_path(project_name)
    payload = {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_outline_discussion_artifact(project_name: str) -> dict:
    path = _outline_discussion_path(project_name)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_outline_discussion_artifact(project_name: str) -> bool:
    path = _outline_discussion_path(project_name)
    if not path.exists():
        return False
    path.unlink()
    sync_project_retrieval_assets(project_name)
    return True


def volumes_path(project_name: str) -> Path:
    path = project_path(project_name) / "volumes"
    path.mkdir(exist_ok=True)
    return path


def _volume_markdown_path(project_name: str, volume_no: int) -> Path:
    return volumes_path(project_name) / f"volume_{volume_no:03d}.md"


def _volume_meta_path(project_name: str, volume_no: int) -> Path:
    return volumes_path(project_name) / f"volume_{volume_no:03d}.meta.json"


def _volume_discussion_path(project_name: str, volume_no: int) -> Path:
    return volumes_path(project_name) / f"volume_{volume_no:03d}.discussion.json"


def arcs_path(project_name: str) -> Path:
    path = project_path(project_name) / "arcs"
    path.mkdir(exist_ok=True)
    return path


def _arc_markdown_path(project_name: str, arc_no: int) -> Path:
    return arcs_path(project_name) / f"arc_{arc_no:03d}.md"


def _arc_meta_path(project_name: str, arc_no: int) -> Path:
    return arcs_path(project_name) / f"arc_{arc_no:03d}.meta.json"


def _arc_discussion_path(project_name: str, arc_no: int) -> Path:
    return arcs_path(project_name) / f"arc_{arc_no:03d}.discussion.json"


def save_volume_outline(project_name: str, volume_no: int, outline: str):
    file = _volume_markdown_path(project_name, volume_no)
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_volume_outline(project_name: str, volume_no: int) -> str:
    file = _volume_markdown_path(project_name, volume_no)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_volume_metadata(project_name: str, volume_no: int, metadata: dict):
    current = load_volume_metadata(project_name, volume_no)
    normalized = VolumeOutlineMetadata.model_validate({**current, **metadata, "volume_no": volume_no})
    file = _volume_meta_path(project_name, volume_no)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_volume_discussion_artifact(project_name: str, volume_no: int, discussion: dict, report_markdown: str):
    file = _volume_discussion_path(project_name, volume_no)
    payload = {
        "volume_no": volume_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))})
    sync_project_retrieval_assets(project_name)


def load_volume_discussion_artifact(project_name: str, volume_no: int) -> dict:
    file = _volume_discussion_path(project_name, volume_no)
    if not file.exists():
        return {}
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "volume_no": volume_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_volume_discussion_artifact(project_name: str, volume_no: int) -> bool:
    file = _volume_discussion_path(project_name, volume_no)
    if not file.exists():
        return False
    file.unlink()
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": False})
    sync_project_retrieval_assets(project_name)
    return True


def load_volume_metadata(project_name: str, volume_no: int) -> dict:
    file = _volume_meta_path(project_name, volume_no)
    fallback = VolumeOutlineMetadata(volume_no=volume_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return VolumeOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def list_volumes(project_name: str) -> list[dict]:
    path = volumes_path(project_name)
    volume_numbers: set[int] = set()
    for file in path.glob("volume_*.md"):
        try:
            volume_numbers.add(int(file.stem.split("_")[-1]))
        except Exception:
            continue
    for file in path.glob("volume_*.meta.json"):
        try:
            volume_numbers.add(int(file.name.replace("volume_", "").replace(".meta.json", "")))
        except Exception:
            continue

    items = []
    for volume_no in sorted(volume_numbers):
        metadata = load_volume_metadata(project_name, volume_no)
        outline = load_volume_outline(project_name, volume_no)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_volume(project_name: str, volume_no: int) -> bool:
    deleted = False
    markdown_path = _volume_markdown_path(project_name, volume_no)
    meta_path = _volume_meta_path(project_name, volume_no)
    discussion_path = _volume_discussion_path(project_name, volume_no)
    if markdown_path.exists():
        markdown_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    if discussion_path.exists():
        discussion_path.unlink()
        deleted = True
    if deleted:
        chapter_outline_dir = project_path(project_name) / "chapter_outlines"
        if chapter_outline_dir.exists():
            for file in chapter_outline_dir.glob("chapter_*.meta.json"):
                try:
                    payload = json.loads(file.read_text(encoding="utf-8"))
                    normalized = ChapterOutlineMetadata.model_validate(payload).model_dump()
                except Exception:
                    continue
                if normalized.get("volume_no") != volume_no:
                    continue
                normalized["volume_no"] = None
                if normalized.get("arc_no") is not None:
                    normalized["arc_no"] = None
                file.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def save_arc_outline(project_name: str, arc_no: int, outline: str):
    file = _arc_markdown_path(project_name, arc_no)
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_arc_outline(project_name: str, arc_no: int) -> str:
    file = _arc_markdown_path(project_name, arc_no)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_arc_metadata(project_name: str, arc_no: int, metadata: dict):
    current = load_arc_metadata(project_name, arc_no)
    normalized = ArcOutlineMetadata.model_validate({**current, **metadata, "arc_no": arc_no})
    file = _arc_meta_path(project_name, arc_no)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_arc_discussion_artifact(project_name: str, arc_no: int, discussion: dict, report_markdown: str):
    file = _arc_discussion_path(project_name, arc_no)
    payload = {
        "arc_no": arc_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))})
    sync_project_retrieval_assets(project_name)


def load_arc_discussion_artifact(project_name: str, arc_no: int) -> dict:
    file = _arc_discussion_path(project_name, arc_no)
    if not file.exists():
        return {}
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "arc_no": arc_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_arc_discussion_artifact(project_name: str, arc_no: int) -> bool:
    file = _arc_discussion_path(project_name, arc_no)
    if not file.exists():
        return False
    file.unlink()
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": False})
    sync_project_retrieval_assets(project_name)
    return True


def load_arc_metadata(project_name: str, arc_no: int) -> dict:
    file = _arc_meta_path(project_name, arc_no)
    fallback = ArcOutlineMetadata(arc_no=arc_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return ArcOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def list_arcs(project_name: str, volume_no: int | None = None) -> list[dict]:
    path = arcs_path(project_name)
    arc_numbers: set[int] = set()
    for file in path.glob("arc_*.md"):
        try:
            arc_numbers.add(int(file.stem.split("_")[-1]))
        except Exception:
            continue
    for file in path.glob("arc_*.meta.json"):
        try:
            arc_numbers.add(int(file.name.replace("arc_", "").replace(".meta.json", "")))
        except Exception:
            continue

    items = []
    for arc_no in sorted(arc_numbers):
        metadata = load_arc_metadata(project_name, arc_no)
        if volume_no is not None and metadata.get("volume_no") != volume_no:
            continue
        outline = load_arc_outline(project_name, arc_no)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_arc(project_name: str, arc_no: int) -> bool:
    deleted = False
    markdown_path = _arc_markdown_path(project_name, arc_no)
    meta_path = _arc_meta_path(project_name, arc_no)
    discussion_path = _arc_discussion_path(project_name, arc_no)
    if markdown_path.exists():
        markdown_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    if discussion_path.exists():
        discussion_path.unlink()
        deleted = True
    if deleted:
        chapter_outline_dir = project_path(project_name) / "chapter_outlines"
        if chapter_outline_dir.exists():
            for file in chapter_outline_dir.glob("chapter_*.meta.json"):
                try:
                    payload = json.loads(file.read_text(encoding="utf-8"))
                    normalized = ChapterOutlineMetadata.model_validate(payload).model_dump()
                except Exception:
                    continue
                if normalized.get("arc_no") != arc_no:
                    continue
                normalized["arc_no"] = None
                file.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def _chapter_outline_meta_path(project_name: str, chapter_no: int) -> Path:
    path = project_path(project_name) / "chapter_outlines"
    path.mkdir(exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.meta.json"


def _chapter_discussion_path(project_name: str, chapter_no: int) -> Path:
    path = project_path(project_name) / "chapter_outlines"
    path.mkdir(exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.discussion.json"


def save_chapter_outline(project_name: str, chapter_no: int, outline: str):
    path = project_path(project_name) / "chapter_outlines"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_chapter_outline_metadata(project_name: str, chapter_no: int, metadata: dict):
    normalized = ChapterOutlineMetadata.model_validate({**metadata, "chapter_no": chapter_no})
    file = _chapter_outline_meta_path(project_name, chapter_no)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_chapter_discussion_artifact(project_name: str, chapter_no: int, discussion: dict, report_markdown: str):
    file = _chapter_discussion_path(project_name, chapter_no)
    payload = {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_chapter_discussion_artifact(project_name: str, chapter_no: int) -> dict:
    file = _chapter_discussion_path(project_name, chapter_no)
    if not file.exists():
        return {}
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_chapter_discussion_artifact(project_name: str, chapter_no: int) -> bool:
    file = _chapter_discussion_path(project_name, chapter_no)
    if not file.exists():
        return False
    file.unlink()
    sync_project_retrieval_assets(project_name)
    return True


def load_chapter_outline_metadata(project_name: str, chapter_no: int) -> dict:
    file = _chapter_outline_meta_path(project_name, chapter_no)
    fallback = ChapterOutlineMetadata(chapter_no=chapter_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return ChapterOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def load_chapter_outline(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "chapter_outlines" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_chapter(project_name: str, chapter_no: int, content: str):
    path = project_path(project_name) / "chapters"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_chapter(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "chapters" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_review(project_name: str, chapter_no: int, content: str):
    path = project_path(project_name) / "reviews"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_review(project_name: str, chapter_no: int) -> str:
    file = project_path(project_name) / "reviews" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


DEFAULT_SUMMARY_LIMIT = 5

def get_recent_chapter_summaries(project_name: str, limit: int = DEFAULT_SUMMARY_LIMIT) -> list[dict]:
    memory = load_memory(project_name)
    summaries = [
        item for item in memory.get("chapter_summaries", [])
        if isinstance(item, dict) and item.get("summary")
    ]
    summaries.sort(key=lambda item: item.get("chapter_no", 0))
    return summaries[-limit:]


def save_review_json(project_name: str, chapter_no: int, data: dict):
    path = project_path(project_name) / "reviews"
    path.mkdir(exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.json"
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_review_json(project_name: str, chapter_no: int) -> dict | None:
    file = project_path(project_name) / "reviews" / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_analysis_report(project_name: str, analysis_type: str, chapter_no: int, content: str):
    path = project_path(project_name) / "analysis"
    path.mkdir(exist_ok=True)
    file = path / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_analysis_report(project_name: str, analysis_type: str, chapter_no: int) -> str:
    file = project_path(project_name) / "analysis" / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def runs_path(project_name: str) -> Path:
    path = project_path(project_name) / "runs"
    path.mkdir(exist_ok=True)
    return path


def save_pipeline_run(project_name: str, run_id: str, content: str):
    file = runs_path(project_name) / f"{run_id}.json"
    file.write_text(content, encoding="utf-8")


def load_pipeline_run(project_name: str, run_id: str) -> str:
    file = runs_path(project_name) / f"{run_id}.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def list_pipeline_runs(project_name: str, chapter_no: int | None = None) -> list[str]:
    path = runs_path(project_name)
    files = sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if chapter_no is None:
        return [file.stem for file in files]
    chapter_prefix = f"chapter_{chapter_no:03d}_"
    return [file.stem for file in files if file.stem.startswith(chapter_prefix)]


def retrieval_path(project_name: str) -> Path:
    path = project_path(project_name) / "retrieval"
    path.mkdir(exist_ok=True)
    return path


def retrieval_sources_path(project_name: str) -> Path:
    path = retrieval_path(project_name) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_retrieval_source_files(project_name: str) -> list[str]:
    path = retrieval_sources_path(project_name)
    files = [file.relative_to(path).as_posix() for file in path.rglob("*") if file.is_file()]
    return sorted(files, key=str.lower)


def delete_retrieval_source_file(project_name: str, relative_path: str) -> bool:
    base_path = retrieval_sources_path(project_name).resolve()
    target = (base_path / relative_path).resolve()
    if base_path not in target.parents and target != base_path:
        raise ValueError("Invalid retrieval source path.")
    if not target.exists() or not target.is_file():
        return False
    target.unlink()
    return True


def save_retrieval_manifest(project_name: str, content: str):
    file = retrieval_path(project_name) / "manifest.json"
    file.write_text(content, encoding="utf-8")


def load_retrieval_manifest(project_name: str) -> str:
    file = retrieval_path(project_name) / "manifest.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_retrieval_vectors(project_name: str, content: str):
    file = retrieval_path(project_name) / "vectors.json"
    file.write_text(content, encoding="utf-8")


def load_retrieval_vectors(project_name: str) -> str:
    file = retrieval_path(project_name) / "vectors.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def chapter_count(project_name: str) -> int:
    chapters_dir = project_path(project_name) / "chapters"
    if not chapters_dir.exists():
        return 0
    return len([f for f in chapters_dir.iterdir() if f.suffix == ".md"])
