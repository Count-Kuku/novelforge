import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import dotenv_values

from schemas import ArcOutlineMetadata, ChapterOutlineMetadata, ConflictResolution, CreativeProfile, StoryMeta, StoriesIndex, VolumeOutlineMetadata

BASE_DIR = Path("data/projects")
GLOBAL_RULES_PATH = Path("data/global_rules.json")
GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH = Path("data/global_rule_conflict_resolutions.json")
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
    "chapter_summaries": [],
    "locations": [],
    "organizations": [],
    "power_systems": [],
    "relationship_graph": [],
}
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
    try:
        from llm import clear_llm_client_cache

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


def normalize_project_name(project_name: str) -> str:
    normalized = project_name.strip()
    if not normalized:
        raise ValueError("Project name cannot be empty.")
    if ".." in normalized or "/" in normalized or "\\" in normalized:
        raise ValueError("Invalid project name: path traversal characters not allowed.")
    return normalized


def project_dir(project_name: str) -> Path:
    return BASE_DIR / normalize_project_name(project_name)


def project_path(project_name: str) -> Path:
    path = project_dir(project_name)
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_project(project_name: str) -> str:
    normalized_name = project_name.strip()
    if not normalized_name:
        raise ValueError("Project name cannot be empty.")

    project_path(normalized_name)
    load_memory(normalized_name)
    load_creative_profile(normalized_name)
    load_project_rules(normalized_name)
    knowledge_dir_path(normalized_name)
    save_pending_knowledge_items(normalized_name, load_pending_knowledge_items(normalized_name))
    long_reference_batches_path(normalized_name)
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

    for key in ["au_rules", "world", "characters", "relationships", "timeline", "foreshadowing", "active_constraints", "chapter_summaries", "locations", "organizations", "power_systems", "relationship_graph"]:
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
    except Exception as exc:
        import logging

        logging.getLogger("novelforge").warning(
            "Failed to sync retrieval assets for project %s: %s",
            project_name, exc,
        )


def load_memory(project_name: str) -> dict:
    path = project_path(project_name) / "memory.json"

    if not path.exists():
        memory = normalize_memory(project_name, None)
        save_memory(project_name, memory)
        return memory

    try:
        memory = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        memory = normalize_memory(project_name, None)
        save_memory(project_name, memory)
        return memory
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


def creative_profile_path(project_name: str, story_id: str = "default") -> Path:
    return _story_path_from_project_path(project_name, story_id, "creative_profile.json")


def load_creative_profile(project_name: str, story_id: str = "default") -> dict:
    path = creative_profile_path(project_name, story_id)
    if not path.exists():
        profile = CreativeProfile().model_dump()
        save_creative_profile(project_name, profile, story_id)
        return profile

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    profile = CreativeProfile.model_validate(raw).model_dump()
    if isinstance(raw, dict) and raw and "is_configured" not in raw:
        profile["is_configured"] = True
    if profile != raw:
        save_creative_profile(project_name, profile, story_id)
    return profile


def save_creative_profile(project_name: str, profile: dict, story_id: str = "default", mark_configured: bool | None = None) -> dict:
    normalized = CreativeProfile.model_validate(profile or {}).model_dump()
    if mark_configured is not None:
        normalized["is_configured"] = bool(mark_configured)
    path = creative_profile_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def _creative_profile_discussion_path(project_name: str, story_id: str = "default") -> Path:
    return _story_path_from_project_path(project_name, story_id, "creative_profile.discussion.json")


def save_creative_profile_discussion_artifact(project_name: str, discussion: dict, report_markdown: str, story_id: str = "default"):
    path = _creative_profile_discussion_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_creative_profile_discussion_artifact(project_name: str, story_id: str = "default") -> dict:
    path = _creative_profile_discussion_path(project_name, story_id)
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


def delete_creative_profile_discussion_artifact(project_name: str, story_id: str = "default") -> bool:
    path = _creative_profile_discussion_path(project_name, story_id)
    if not path.exists():
        return False
    path.unlink()
    sync_project_retrieval_assets(project_name)
    return True


# ---------------------------------------------------------------------------
# Story spaces
# ---------------------------------------------------------------------------

def _story_id_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]", "", str(name or "untitled").strip())
    return slug[:48] or "untitled"


def stories_index_path(project_name: str) -> Path:
    return project_path(project_name) / "stories" / "index.json"


def story_path(project_name: str, story_id: str) -> Path:
    return project_path(project_name) / "stories" / story_id


def _story_chapter_summaries_path(project_name: str, story_id: str) -> Path:
    return story_path(project_name, story_id) / "chapter_summaries.json"


def _story_memory_overrides_path(project_name: str, story_id: str) -> Path:
    return story_path(project_name, story_id) / "memory_overrides.json"


def _story_rules_overrides_path(project_name: str, story_id: str) -> Path:
    return story_path(project_name, story_id) / "rules_overrides.json"


def _project_rule_conflict_resolutions_path(project_name: str) -> Path:
    return project_path(project_name) / "rule_conflict_resolutions.json"


def _story_rule_conflict_resolutions_path(project_name: str, story_id: str) -> Path:
    return story_path(project_name, story_id) / "rule_conflict_resolutions.json"


def load_stories_index(project_name: str) -> dict:
    path = stories_index_path(project_name)
    if not path.exists():
        default_story = StoryMeta(
            story_id="default",
            name="默认故事",
            description="",
            status="active",
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        idx = StoriesIndex(stories=[default_story], active_story_id="default")
        save_stories_index(project_name, idx.model_dump())
        return idx.model_dump()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return StoriesIndex.model_validate(raw).model_dump()
    except Exception:
        return StoriesIndex().model_dump()


def save_stories_index(project_name: str, index: dict):
    normalized = StoriesIndex.model_validate(index or {}).model_dump()
    path = stories_index_path(project_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def get_active_story_id(project_name: str) -> str:
    index = load_stories_index(project_name)
    return str(index.get("active_story_id", "default") or "default")


def set_active_story(project_name: str, story_id: str):
    index = load_stories_index(project_name)
    story_ids = {s["story_id"] for s in index.get("stories", [])}
    if story_id not in story_ids:
        raise ValueError(f"故事不存在：{story_id}")
    index["active_story_id"] = story_id
    save_stories_index(project_name, index)


def create_story(project_name: str, name: str, description: str = "") -> dict:
    index = load_stories_index(project_name)
    story_id = _story_id_slug(name)
    existing_ids = {s["story_id"] for s in index.get("stories", [])}
    if story_id in existing_ids:
        counter = 2
        while f"{story_id}_{counter}" in existing_ids:
            counter += 1
            if counter > 1000:
                raise RuntimeError(f"无法为故事名 '{name}' 生成唯一 ID：计数器已超上限。")
        story_id = f"{story_id}_{counter}"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = StoryMeta(
        story_id=story_id,
        name=name,
        description=description,
        status="active",
        created_at=now,
        updated_at=now,
    )
    stories = index.get("stories", [])
    stories.append(meta.model_dump())
    index["stories"] = stories
    if not index.get("active_story_id") or index["active_story_id"] == "default":
        index["active_story_id"] = story_id
    save_stories_index(project_name, index)
    sp = story_path(project_name, story_id)
    sp.mkdir(parents=True, exist_ok=True)
    return meta.model_dump()


def rename_story(project_name: str, story_id: str, name: str, description: str | None = None) -> dict:
    clean_story_id = str(story_id or "").strip()
    clean_name = str(name or "").strip()
    if not clean_story_id:
        raise ValueError("故事 ID 不能为空。")
    if not clean_name:
        raise ValueError("故事名称不能为空。")

    index = load_stories_index(project_name)
    for story in index.get("stories", []):
        if story.get("story_id") == clean_story_id:
            story["name"] = clean_name
            if description is not None:
                story["description"] = str(description or "").strip()
            story["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_stories_index(project_name, index)
            return dict(story)
    raise ValueError(f"故事不存在：{clean_story_id}")



def copy_story_settings(project_name: str, source_story_id: str, target_story_id: str):
    """将源故事的创作配置、创作配置讨论工件、记忆覆盖和生成规则复制到目标故事。"""
    from shutil import copy2

    src_profile = creative_profile_path(project_name, source_story_id)
    if src_profile.exists():
        dst_profile = creative_profile_path(project_name, target_story_id)
        dst_profile.parent.mkdir(parents=True, exist_ok=True)
        copy2(str(src_profile), str(dst_profile))

    src_discussion = _creative_profile_discussion_path(project_name, source_story_id)
    if src_discussion.exists():
        dst_discussion = _creative_profile_discussion_path(project_name, target_story_id)
        dst_discussion.parent.mkdir(parents=True, exist_ok=True)
        copy2(str(src_discussion), str(dst_discussion))

    src_overrides = _story_memory_overrides_path(project_name, source_story_id)
    if src_overrides.exists():
        dst_overrides = _story_memory_overrides_path(project_name, target_story_id)
        dst_overrides.parent.mkdir(parents=True, exist_ok=True)
        copy2(str(src_overrides), str(dst_overrides))

    src_rules = _story_rules_overrides_path(project_name, source_story_id)
    if src_rules.exists():
        dst_rules = _story_rules_overrides_path(project_name, target_story_id)
        dst_rules.parent.mkdir(parents=True, exist_ok=True)
        copy2(str(src_rules), str(dst_rules))

    src_rule_conflicts = _story_rule_conflict_resolutions_path(project_name, source_story_id)
    if src_rule_conflicts.exists():
        dst_rule_conflicts = _story_rule_conflict_resolutions_path(project_name, target_story_id)
        dst_rule_conflicts.parent.mkdir(parents=True, exist_ok=True)
        copy2(str(src_rule_conflicts), str(dst_rule_conflicts))

    sync_project_retrieval_assets(project_name)


def _merge_list_values(source: list | None, target: list | None) -> list:
    seen: set[str] = set()
    merged: list = []
    for item in (source or []) + (target or []):
        if item is None:
            continue
        if isinstance(item, dict):
            key = str(item.get("name") or item.get("title") or "").strip()
            if not key:
                merged.append(item)
                continue
        else:
            key = str(item).strip()
            if not key:
                merged.append(item)
                continue
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def merge_story_to_project_memory(project_name: str, story_id: str, field_resolutions: dict[str, Any] | None = None) -> dict:
    from merge import build_merge_plan

    base = load_memory(project_name)
    story = load_story_memory(project_name, story_id)
    plan = build_merge_plan(story, base, source_label="故事", target_label="项目", base_path="memory")
    resolved = {}
    for opt in plan:
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[opt.path.replace("memory.", "")] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[opt.path.replace("memory.", "")] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[opt.path.replace("memory.", "")] = field_resolutions[opt.path]
        else:
            resolved[opt.path.replace("memory.", "")] = opt.source_value

    merged = dict(base)
    for key, value in resolved.items():
        merged[key] = value
    save_memory(project_name, merged)

    overrides_path = _story_memory_overrides_path(project_name, story_id)
    if overrides_path.exists():
        overrides_path.unlink()
    sync_project_retrieval_assets(project_name)
    return merged


def merge_project_to_story_memory(project_name: str, story_id: str, field_resolutions: dict[str, Any] | None = None) -> dict:
    from merge import build_merge_plan

    base = load_memory(project_name)
    story = load_story_memory(project_name, story_id)
    plan = build_merge_plan(base, story, source_label="项目", target_label="故事", base_path="memory")
    resolved = {}
    for opt in plan:
        key = opt.path.replace("memory.", "")
        if key == "chapter_summaries":
            continue
        if not opt.conflict:
            if opt.field_type == "list":
                resolved[key] = _merge_list_values(opt.source_value, opt.target_value)
            else:
                resolved[key] = opt.source_value if opt.source_value is not None else opt.target_value
        elif field_resolutions and opt.path in field_resolutions:
            resolved[key] = field_resolutions[opt.path]
        else:
            resolved[key] = opt.source_value

    overrides: dict = {}
    for key, value in resolved.items():
        if base.get(key) != value:
            overrides[key] = value
    path = _story_memory_overrides_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)
    return {**base, **overrides}


def merge_story_rules_to_project(project_name: str, story_id: str) -> dict:
    project_rules = load_project_rules(project_name)
    story_rules = load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(project_rules, story_rules)
    save_project_rules(project_name, merged)
    path = _story_rules_overrides_path(project_name, story_id)
    if path.exists():
        path.unlink()
    return merged


def merge_project_rules_to_story(project_name: str, story_id: str) -> dict:
    project_rules = load_project_rules(project_name)
    save_story_rules(project_name, story_id, project_rules)
    return project_rules


def _merge_rules_dedup(target_rules: dict, source_rules: dict) -> dict:
    from merge import _merge_dedup

    merged = dict(target_rules)
    for scope in RULE_SCOPES:
        source_items = source_rules.get(scope, [])
        if source_items:
            existing = merged.get(scope, [])
            merged[scope] = _merge_dedup(existing, source_items)
    return normalize_rules(merged)


def merge_project_rules_to_global(project_name: str) -> dict:
    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    merged = _merge_rules_dedup(global_rules, project_rules)
    save_global_rules(merged)
    return merged


def merge_story_rules_to_global(project_name: str, story_id: str) -> dict:
    global_rules = load_global_rules()
    story_rules = load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(global_rules, story_rules)
    save_global_rules(merged)
    return merged


def merge_global_rules_to_project(project_name: str) -> dict:
    global_rules = load_global_rules()
    project_rules = load_project_rules(project_name)
    merged = _merge_rules_dedup(project_rules, global_rules)
    save_project_rules(project_name, merged)
    return merged


def merge_global_rules_to_story(project_name: str, story_id: str) -> dict:
    global_rules = load_global_rules()
    story_rules = load_story_rules(project_name, story_id)
    merged = _merge_rules_dedup(story_rules, global_rules)
    save_story_rules(project_name, story_id, merged)
    return merged


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
        if scope not in RULE_SCOPES:
            scope = "all"
        title = str(item.get("title", "") or "").strip() or decision[:40]
        payload = {
            "id": str(item.get("id", "") or uuid4()).strip(),
            "scope": scope,
            "title": title,
            "decision": decision,
            "updated_at": str(item.get("updated_at", "") or datetime.now(timezone.utc).isoformat(timespec="seconds")),
        }
        if source:
            payload["source"] = source
        normalized.append(payload)
    return normalized


def _rule_conflict_resolution_path(project_name: str, layer: str, story_id: str = "default") -> Path:
    if layer == "global":
        return GLOBAL_RULE_CONFLICT_RESOLUTIONS_PATH
    if layer == "story":
        return _story_rule_conflict_resolutions_path(project_name, story_id)
    return _project_rule_conflict_resolutions_path(project_name)


def load_rule_conflict_resolutions(project_name: str, layer: str = "story", story_id: str = "default") -> list[dict]:
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return normalize_rule_conflict_resolutions(raw if isinstance(raw, list) else None)


def save_rule_conflict_resolutions(project_name: str, layer: str, resolutions: list[dict], story_id: str = "default") -> list[dict]:
    path = _rule_conflict_resolution_path(project_name, layer, story_id)
    normalized = normalize_rule_conflict_resolutions(resolutions)
    if not normalized:
        if path.exists():
            path.unlink()
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def add_rule_conflict_resolution(
    project_name: str,
    layer: str,
    scope: str,
    title: str,
    decision: str,
    story_id: str = "default",
) -> dict:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id)
    normalized_items = normalize_rule_conflict_resolutions([{
        "id": str(uuid4()),
        "scope": scope,
        "title": title,
        "decision": decision,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }])
    if not normalized_items:
        raise ValueError("Conflict resolution decision cannot be empty.")
    item = normalized_items[0]
    existing.append(item)
    save_rule_conflict_resolutions(project_name, layer, existing, story_id)
    return item


def delete_rule_conflict_resolution(project_name: str, layer: str, resolution_id: str, story_id: str = "default") -> bool:
    existing = load_rule_conflict_resolutions(project_name, layer, story_id)
    kept = [item for item in existing if item.get("id") != resolution_id]
    if len(kept) == len(existing):
        return False
    save_rule_conflict_resolutions(project_name, layer, kept, story_id)
    return True


def load_effective_rule_conflict_resolutions(project_name: str, story_id: str, scope: str) -> list[dict]:
    effective: list[dict] = []
    for layer, source_label in [("global", "全局"), ("project", "项目"), ("story", "故事")]:
        for item in load_rule_conflict_resolutions(project_name, layer, story_id):
            item_scope = item.get("scope", "all")
            if item_scope in {"all", scope}:
                normalized = dict(item)
                normalized["source"] = source_label
                effective.append(normalized)
    return effective


def copy_story(project_name: str, source_story_id: str, new_name: str,
               *, include_discussions: bool = True, include_summaries: bool = True,
               include_chapters: bool = True) -> dict:
    import shutil

    meta = create_story(project_name, new_name)
    target_id = meta["story_id"]
    src_dir = story_path(project_name, source_story_id)
    dst_dir = story_path(project_name, target_id)
    dst_dir.mkdir(parents=True, exist_ok=True)

    copy_story_settings(project_name, source_story_id, target_id)

    for item in src_dir.iterdir():
        if item.is_dir():
            if not include_chapters and item.name in {"chapters", "chapter_outlines", "reviews", "analysis", "evaluation", "runs"}:
                continue
            if not include_discussions and item.name in {"volumes", "arcs"}:
                continue
            shutil.copytree(str(item), str(dst_dir / item.name), dirs_exist_ok=True)
        elif item.is_file():
            if not include_summaries and item.name == "chapter_summaries.json":
                continue
            if not include_discussions and "discussion" in item.name:
                continue
            shutil.copy2(str(item), str(dst_dir / item.name))

    sync_project_retrieval_assets(project_name)
    return meta


def archive_story(project_name: str, story_id: str) -> bool:
    index = load_stories_index(project_name)
    for s in index.get("stories", []):
        if s["story_id"] == story_id:
            s["status"] = "archived"
            s["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save_stories_index(project_name, index)
            return True
    return False


def delete_story(project_name: str, story_id: str) -> bool:
    index = load_stories_index(project_name)
    before = len(index.get("stories", []))
    index["stories"] = [s for s in index.get("stories", []) if s["story_id"] != story_id]
    if len(index["stories"]) == before:
        return False
    if index.get("active_story_id") == story_id:
        if index["stories"]:
            index["active_story_id"] = index["stories"][0]["story_id"]
        else:
            default = StoryMeta(
                story_id="default",
                name="默认故事",
                description="",
                status="active",
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                updated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
            index["stories"].append(default.model_dump())
            index["active_story_id"] = "default"
    save_stories_index(project_name, index)
    sp = story_path(project_name, story_id)
    if sp.exists():
        import shutil
        shutil.rmtree(str(sp))
    sync_project_retrieval_assets(project_name)
    return True


def list_stories(project_name: str) -> list[dict]:
    index = load_stories_index(project_name)
    return list(index.get("stories", []))


def load_story_memory(project_name: str, story_id: str) -> dict:
    base = load_memory(project_name)
    overrides_path = _story_memory_overrides_path(project_name, story_id)
    if not overrides_path.exists():
        return base
    try:
        overrides = json.loads(overrides_path.read_text(encoding="utf-8"))
    except Exception:
        return base
    if not isinstance(overrides, dict):
        return base
    merged = dict(base)
    for key, value in overrides.items():
        if isinstance(value, list) and isinstance(base.get(key), list):
            # 基于 key 去重合并，防止前缀匹配优化未命中时产生重复条目
            seen: set[str] = set()
            deduped: list = []
            for item in base[key] + value:
                item_key = str(item.get("name") or item.get("title") or item) if isinstance(item, dict) else str(item)
                if item_key not in seen:
                    seen.add(item_key)
                    deduped.append(item)
            merged[key] = deduped
        elif value is not None:
            merged[key] = value
    return merged


def save_story_memory(project_name: str, story_id: str, memory: dict):
    if story_id == "default":
        save_memory(project_name, memory)
        return

    base = load_memory(project_name)
    overrides: dict = {}
    for key, value in (memory or {}).items():
        base_value = base.get(key)
        if value == base_value:
            continue
        # 使用前缀匹配检测仅追加的新条目；若条目被插入到列表开头或中间，则整体值会存入覆盖层，
        # 下次加载时会基于 key 去重合并，因此数据一致性不会受损。
        if isinstance(value, list) and isinstance(base_value, list) and value[:len(base_value)] == base_value:
            extra_items = value[len(base_value):]
            if extra_items:
                overrides[key] = extra_items
        else:
            overrides[key] = value

    path = _story_memory_overrides_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_story_chapter_summaries(project_name: str, story_id: str) -> list[dict]:
    path = _story_chapter_summaries_path(project_name, story_id)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw) if isinstance(raw, list) else []
    except Exception:
        return []


def save_story_chapter_summaries(project_name: str, story_id: str, summaries: list[dict]):
    path = _story_chapter_summaries_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(summaries or []), ensure_ascii=False, indent=2), encoding="utf-8")


def migrate_project_to_stories(project_name: str) -> bool:
    marker = project_path(project_name) / ".migrated"
    if marker.exists():
        return False
    sp = story_path(project_name, "default")
    sp.mkdir(parents=True, exist_ok=True)

    migratable = [
        ("outline.md", "outline.md"),
        ("outline.discussion.json", "outline.discussion.json"),
        ("creative_profile.json", "creative_profile.json"),
        ("creative_profile.discussion.json", "creative_profile.discussion.json"),
        ("volumes", "volumes"),
        ("arcs", "arcs"),
        ("chapter_outlines", "chapter_outlines"),
        ("chapters", "chapters"),
        ("reviews", "reviews"),
        ("analysis", "analysis"),
        ("evaluation", "evaluation"),
        ("runs", "runs"),
    ]
    moved_any = False
    for src_name, dst_name in migratable:
        src = project_path(project_name) / src_name
        dst = sp / dst_name
        if src.exists():
            if dst.exists():
                continue
            src.rename(dst)
            moved_any = True

    conflict_src = project_path(project_name) / "retrieval" / "conflict_resolutions.json"
    conflict_dst = sp / "retrieval" / "conflict_resolutions.json"
    if conflict_src.exists():
        conflict_dst.parent.mkdir(parents=True, exist_ok=True)
        conflict_src.rename(conflict_dst)

    summaries = load_memory(project_name).get("chapter_summaries", [])
    if summaries:
        save_story_chapter_summaries(project_name, "default", list(summaries))

    memory = load_memory(project_name)
    if "chapter_summaries" in memory:
        memory["chapter_summaries"] = []
        save_memory(project_name, memory)

    idx_path = project_path(project_name) / "stories" / "index.json"
    if not idx_path.exists():
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        default_meta = StoryMeta(
            story_id="default",
            name="默认故事",
            description="",
            status="active",
            created_at=now,
            updated_at=now,
        )
        idx = StoriesIndex(stories=[default_meta], active_story_id="default")
        save_stories_index(project_name, idx.model_dump())

    marker.write_text("")
    sync_project_retrieval_assets(project_name)
    return moved_any


def _story_path_from_project_path(project_name: str, story_id: str, *parts: str) -> Path:
    return story_path(project_name, story_id).joinpath(*parts)


def knowledge_dir_path(project_name: str) -> Path:
    path = project_path(project_name) / "knowledge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def knowledge_category_path(project_name: str, category: str) -> Path:
    safe_category = str(category or "").strip()
    if safe_category not in KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    return knowledge_dir_path(project_name) / f"{safe_category}.json"


def knowledge_entities_dir_path(project_name: str) -> Path:
    path = knowledge_dir_path(project_name) / "entities"
    path.mkdir(parents=True, exist_ok=True)
    return path


def character_entities_path(project_name: str) -> Path:
    return knowledge_entities_dir_path(project_name) / "characters.json"


def setting_entities_path(project_name: str) -> Path:
    return knowledge_entities_dir_path(project_name) / "settings.json"


def entity_aliases_path(project_name: str) -> Path:
    return knowledge_entities_dir_path(project_name) / "aliases.json"


def extraction_plan_templates_path(project_name: str) -> Path:
    return knowledge_entities_dir_path(project_name) / "extraction_plans.json"


def pending_knowledge_path(project_name: str) -> Path:
    return knowledge_dir_path(project_name) / "pending.json"


def auto_review_runs_path(project_name: str) -> Path:
    return knowledge_dir_path(project_name) / "auto_review_runs.json"


def auto_review_policy_path(project_name: str) -> Path:
    return knowledge_dir_path(project_name) / "auto_review_policy.json"


DEFAULT_AUTO_REVIEW_POLICY = {
    "min_confidence": 0.45,
    "min_evidence_strength": 0.35,
    "grade_a_confidence": 0.75,
    "grade_a_evidence_strength": 0.65,
    "allow_grade_b_auto_confirm": True,
    "require_evidence": True,
    "manual_review_categories": ["constraints"],
}


def _load_json_list(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def load_knowledge_category(project_name: str, category: str) -> list[dict]:
    return _load_json_list(knowledge_category_path(project_name, category))


def save_knowledge_category(project_name: str, category: str, items: list[dict]):
    path = knowledge_category_path(project_name, category)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_knowledge_base(project_name: str) -> dict[str, list[dict]]:
    return {
        category: load_knowledge_category(project_name, category)
        for category in KNOWLEDGE_CATEGORIES
    }


def load_character_entities(project_name: str) -> list[dict]:
    return _load_json_list(character_entities_path(project_name))


def save_character_entities(project_name: str, items: list[dict]):
    path = character_entities_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_setting_entities(project_name: str) -> list[dict]:
    return _load_json_list(setting_entities_path(project_name))


def save_setting_entities(project_name: str, items: list[dict]):
    path = setting_entities_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_entity_aliases(project_name: str) -> list[dict]:
    return _load_json_list(entity_aliases_path(project_name))


def save_entity_aliases(project_name: str, items: list[dict]):
    path = entity_aliases_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_extraction_plan_templates(project_name: str) -> list[dict]:
    return _load_json_list(extraction_plan_templates_path(project_name))


def save_extraction_plan_templates(project_name: str, items: list[dict]):
    path = extraction_plan_templates_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_pending_knowledge_items(project_name: str) -> list[dict]:
    return _load_json_list(pending_knowledge_path(project_name))


def save_pending_knowledge_items(project_name: str, items: list[dict]):
    path = pending_knowledge_path(project_name)
    normalized = [item for item in items if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def load_auto_review_runs(project_name: str) -> list[dict]:
    return _load_json_list(auto_review_runs_path(project_name))


def save_auto_review_runs(project_name: str, runs: list[dict]):
    path = auto_review_runs_path(project_name)
    normalized = [item for item in runs if isinstance(item, dict)]
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_auto_review_policy(policy: dict | None) -> dict:
    raw = policy if isinstance(policy, dict) else {}
    normalized = dict(DEFAULT_AUTO_REVIEW_POLICY)
    for key in ["min_confidence", "min_evidence_strength", "grade_a_confidence", "grade_a_evidence_strength"]:
        try:
            value = float(raw.get(key, normalized[key]))
        except (TypeError, ValueError):
            value = float(normalized[key])
        normalized[key] = max(0.0, min(1.0, value))
    normalized["allow_grade_b_auto_confirm"] = bool(raw.get("allow_grade_b_auto_confirm", normalized["allow_grade_b_auto_confirm"]))
    normalized["require_evidence"] = bool(raw.get("require_evidence", normalized["require_evidence"]))
    categories = raw.get("manual_review_categories", normalized["manual_review_categories"])
    if not isinstance(categories, list):
        categories = normalized["manual_review_categories"]
    normalized["manual_review_categories"] = [
        str(category)
        for category in categories
        if str(category) in KNOWLEDGE_CATEGORIES
    ]
    return normalized


def load_auto_review_policy(project_name: str) -> dict:
    path = auto_review_policy_path(project_name)
    if not path.exists():
        return dict(DEFAULT_AUTO_REVIEW_POLICY)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    return normalize_auto_review_policy(raw)


def save_auto_review_policy(project_name: str, policy: dict) -> dict:
    normalized = normalize_auto_review_policy(policy)
    path = auto_review_policy_path(project_name)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def append_auto_review_run(project_name: str, run: dict) -> dict:
    runs = load_auto_review_runs(project_name)
    normalized = dict(run or {})
    normalized["run_id"] = normalized.get("run_id") or f"auto_review_{uuid4().hex}"
    normalized["created_at"] = normalized.get("created_at") or datetime.now(timezone.utc).isoformat()
    normalized["status"] = normalized.get("status") or "active"
    runs.append(normalized)
    save_auto_review_runs(project_name, runs[-200:])
    return normalized


def queue_pending_knowledge_items(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
) -> int:
    pending = load_pending_knowledge_items(project_name)
    pending_index_by_id = {
        str(item.get("pending_id") or ""): index
        for index, item in enumerate(pending)
        if isinstance(item, dict) and str(item.get("pending_id") or "").strip()
    }
    queued_at = datetime.now(timezone.utc).isoformat()
    added_count = 0
    changed = False
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        name = str(item.get("name") or "").strip()
        if category not in KNOWLEDGE_CATEGORIES or not name:
            continue
        normalized = dict(item)
        pending_id = str(normalized.get("pending_id") or f"pending_{uuid4().hex}")
        normalized["pending_id"] = pending_id
        normalized["category"] = category
        normalized["name"] = name
        normalized["scope"] = scope
        normalized["authority"] = authority
        normalized["source_title"] = source_title or normalized.get("source_title", "")
        normalized["source_origin"] = source_origin
        normalized["version_scope"] = normalized.get("version_scope") or ("canon" if scope == "canon" else "project_main")
        normalized["worldline_id"] = normalized.get("worldline_id") or "main"
        normalized["worldline_label"] = normalized.get("worldline_label") or "本项目主线"
        normalized["status"] = "pending"
        existing_index = pending_index_by_id.get(pending_id)
        if existing_index is not None:
            existing_item = pending[existing_index] if isinstance(pending[existing_index], dict) else {}
            normalized["queued_at"] = existing_item.get("queued_at") or queued_at
            normalized["updated_at"] = queued_at
            pending[existing_index] = normalized
        else:
            normalized["queued_at"] = queued_at
            pending.append(normalized)
            pending_index_by_id[pending_id] = len(pending) - 1
            added_count += 1
        changed = True
    if changed:
        save_pending_knowledge_items(project_name, pending)
    return added_count


def discard_pending_knowledge_items(project_name: str, pending_ids: list[str]) -> int:
    id_set = {str(item) for item in pending_ids}
    if not id_set:
        return 0
    pending = load_pending_knowledge_items(project_name)
    remaining = [item for item in pending if str(item.get("pending_id", "")) not in id_set]
    removed_count = len(pending) - len(remaining)
    if removed_count:
        save_pending_knowledge_items(project_name, remaining)
    return removed_count


def confirm_pending_knowledge_items(project_name: str, pending_ids: list[str]) -> int:
    result = confirm_pending_knowledge_items_with_records(project_name, pending_ids)
    return int(result.get("saved_count", 0))


def confirm_pending_knowledge_items_with_records(
    project_name: str,
    pending_ids: list[str],
    *,
    confirmation_metadata: dict | None = None,
) -> dict:
    id_set = {str(item) for item in pending_ids}
    if not id_set:
        return {"saved_count": 0, "confirmed_records": [], "pending_snapshots": []}
    pending = load_pending_knowledge_items(project_name)
    selected = [item for item in pending if str(item.get("pending_id", "")) in id_set]
    remaining = [item for item in pending if str(item.get("pending_id", "")) not in id_set]

    saved_count = 0
    confirmed_records: list[dict] = []
    grouped: dict[tuple[str, str, str, str], list[dict]] = {}
    for item in selected:
        key = (
            str(item.get("scope") or "reference"),
            str(item.get("authority") or "curated"),
            str(item.get("source_title") or ""),
            str(item.get("source_origin") or ""),
        )
        grouped.setdefault(key, []).append(item)
    for (scope, authority, source_title, source_origin), items in grouped.items():
        count, records = append_knowledge_items_with_records(
            project_name,
            items,
            scope=scope,
            authority=authority,
            source_title=source_title,
            source_origin=source_origin,
            confirmation_metadata=confirmation_metadata,
        )
        saved_count += count
        confirmed_records.extend(records)
    if selected:
        save_pending_knowledge_items(project_name, remaining)
    return {
        "saved_count": saved_count,
        "confirmed_records": confirmed_records,
        "pending_snapshots": [dict(item) for item in selected],
    }


def _make_knowledge_id(category: str, index: int) -> str:
    return f"{category}_{index:04d}"


def append_knowledge_items(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    status: str = "confirmed",
) -> int:
    saved_count, _ = append_knowledge_items_with_records(
        project_name,
        items,
        scope=scope,
        authority=authority,
        source_title=source_title,
        source_origin=source_origin,
        status=status,
    )
    return saved_count


def append_knowledge_items_with_records(
    project_name: str,
    items: list[dict],
    *,
    scope: str,
    authority: str,
    source_title: str = "",
    source_origin: str = "",
    status: str = "confirmed",
    confirmation_metadata: dict | None = None,
) -> tuple[int, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        category = str(item.get("category") or "").strip()
        if category not in KNOWLEDGE_CATEGORIES:
            continue
        grouped.setdefault(category, []).append(item)

    saved_count = 0
    saved_records: list[dict] = []
    for category, category_items in grouped.items():
        existing = load_knowledge_category(project_name, category)
        next_index = len(existing) + 1
        for item in category_items:
            normalized = dict(item)
            source_pending_id = str(normalized.get("pending_id") or "")
            normalized.pop("pending_id", None)
            normalized.pop("queued_at", None)
            normalized.setdefault("name", "")
            if not str(normalized.get("name", "")).strip():
                continue
            normalized["id"] = normalized.get("id") or _make_knowledge_id(category, next_index)
            normalized["category"] = category
            normalized["scope"] = scope
            normalized["authority"] = authority
            normalized["source_title"] = source_title or normalized.get("source_title", "")
            normalized["source_origin"] = source_origin
            normalized["version_scope"] = normalized.get("version_scope") or ("canon" if scope == "canon" else "project_main")
            normalized["worldline_id"] = normalized.get("worldline_id") or "main"
            normalized["worldline_label"] = normalized.get("worldline_label") or "本项目主线"
            normalized["status"] = status
            if confirmation_metadata:
                normalized.update({
                    key: value
                    for key, value in confirmation_metadata.items()
                    if str(key).strip()
                })
            if source_pending_id:
                normalized["source_pending_id"] = source_pending_id
            existing.append(normalized)
            saved_records.append({
                "pending_id": source_pending_id,
                "category": category,
                "knowledge_id": normalized.get("id", ""),
                "name": normalized.get("name", ""),
                "source_title": normalized.get("source_title", ""),
                "source_origin": normalized.get("source_origin", ""),
            })
            next_index += 1
            saved_count += 1
        save_knowledge_category(project_name, category, existing)
    return saved_count, saved_records


def rollback_auto_review_run(project_name: str, run_id: str) -> dict:
    target_run_id = str(run_id or "").strip()
    if not target_run_id:
        return {"success": False, "message": "缺少自动审核记录 ID。", "removed_count": 0, "restored_count": 0}

    runs = load_auto_review_runs(project_name)
    run_index = next((index for index, item in enumerate(runs) if str(item.get("run_id") or "") == target_run_id), -1)
    if run_index < 0:
        return {"success": False, "message": "未找到自动审核记录。", "removed_count": 0, "restored_count": 0}

    run = dict(runs[run_index])
    if str(run.get("status") or "") == "rolled_back":
        return {"success": False, "message": "该自动审核记录已经回退过。", "removed_count": 0, "restored_count": 0}

    confirmed_records = run.get("confirmed_records", []) if isinstance(run.get("confirmed_records", []), list) else []
    removed_count = 0
    records_by_category: dict[str, set[str]] = {}
    for record in confirmed_records:
        if not isinstance(record, dict):
            continue
        category = str(record.get("category") or "")
        knowledge_id = str(record.get("knowledge_id") or "")
        if category in KNOWLEDGE_CATEGORIES and knowledge_id:
            records_by_category.setdefault(category, set()).add(knowledge_id)

    for category, id_set in records_by_category.items():
        existing = load_knowledge_category(project_name, category)
        remaining = [item for item in existing if str(item.get("id") or "") not in id_set]
        removed_count += len(existing) - len(remaining)
        if len(remaining) != len(existing):
            save_knowledge_category(project_name, category, remaining)

    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(item.get("pending_id") or "") for item in pending}
    restored_count = 0
    restored_at = datetime.now(timezone.utc).isoformat()
    for snapshot in run.get("pending_snapshots", []) if isinstance(run.get("pending_snapshots", []), list) else []:
        if not isinstance(snapshot, dict):
            continue
        restored = dict(snapshot)
        pending_id = str(restored.get("pending_id") or "")
        if not pending_id:
            restored["pending_id"] = f"pending_rollback_{uuid4().hex}"
            pending_id = str(restored["pending_id"])
        if pending_id in existing_pending_ids:
            continue
        restored["status"] = "pending"
        restored["rollback_from_auto_review_run_id"] = target_run_id
        restored["rolled_back_at"] = restored_at
        pending.append(restored)
        existing_pending_ids.add(pending_id)
        restored_count += 1
    if restored_count:
        save_pending_knowledge_items(project_name, pending)

    run["status"] = "rolled_back"
    run["rolled_back_at"] = restored_at
    run["rollback_result"] = {
        "removed_count": removed_count,
        "restored_count": restored_count,
    }
    runs[run_index] = run
    save_auto_review_runs(project_name, runs)
    sync_project_retrieval_assets(project_name)
    return {
        "success": True,
        "message": f"已回退自动审核记录：删除 {removed_count} 条正式知识，恢复 {restored_count} 条待确认知识。",
        "removed_count": removed_count,
        "restored_count": restored_count,
        "run": run,
    }


def restore_auto_review_snapshots_to_pending(
    project_name: str,
    run_id: str,
    pending_ids: list[str],
    *,
    snapshot_field: str = "manual_review_snapshots",
) -> dict:
    target_run_id = str(run_id or "").strip()
    requested_ids = [str(item or "").strip() for item in pending_ids if str(item or "").strip()]
    if not target_run_id or not requested_ids:
        return {"success": False, "message": "缺少处理记录或待恢复条目。", "restored_count": 0}

    runs = load_auto_review_runs(project_name)
    run_index = next((index for index, item in enumerate(runs) if str(item.get("run_id") or "") == target_run_id), -1)
    if run_index < 0:
        return {"success": False, "message": "未找到处理记录。", "restored_count": 0}

    run = dict(runs[run_index])
    if str(run.get("status") or "") == "rolled_back":
        return {"success": False, "message": "该处理记录已经整批回退，不能重复恢复。", "restored_count": 0}

    snapshots = run.get(snapshot_field, []) if isinstance(run.get(snapshot_field, []), list) else []
    snapshot_by_id = {
        str(snapshot.get("pending_id") or ""): snapshot
        for snapshot in snapshots
        if isinstance(snapshot, dict) and str(snapshot.get("pending_id") or "")
    }
    restored_before = set(
        str(item or "")
        for item in run.get("restored_pending_ids", [])
        if str(item or "").strip()
    )

    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(item.get("pending_id") or "") for item in pending if isinstance(item, dict)}
    restored_count = 0
    skipped_ids: list[str] = []
    restored_ids: list[str] = []
    restored_at = datetime.now(timezone.utc).isoformat()

    for pending_id in requested_ids:
        snapshot = snapshot_by_id.get(pending_id)
        if not snapshot or pending_id in existing_pending_ids or pending_id in restored_before:
            skipped_ids.append(pending_id)
            continue
        restored = dict(snapshot)
        restored["status"] = "pending"
        restored["restored_from_auto_review_run_id"] = target_run_id
        restored["restored_from_snapshot_field"] = snapshot_field
        restored["restored_at"] = restored_at
        pending.append(restored)
        existing_pending_ids.add(pending_id)
        restored_before.add(pending_id)
        restored_ids.append(pending_id)
        restored_count += 1

    if restored_count:
        save_pending_knowledge_items(project_name, pending)

    run["restored_pending_ids"] = sorted(restored_before)
    restore_events = run.get("restore_events", [])
    if not isinstance(restore_events, list):
        restore_events = []
    restore_events.append({
        "restored_at": restored_at,
        "snapshot_field": snapshot_field,
        "requested_ids": requested_ids,
        "restored_ids": restored_ids,
        "skipped_ids": skipped_ids,
    })
    run["restore_events"] = restore_events[-50:]
    runs[run_index] = run
    save_auto_review_runs(project_name, runs)

    return {
        "success": True,
        "message": f"已恢复 {restored_count} 条到待确认队列，跳过 {len(skipped_ids)} 条。",
        "restored_count": restored_count,
        "skipped_count": len(skipped_ids),
        "restored_ids": restored_ids,
        "skipped_ids": skipped_ids,
    }


def return_confirmed_knowledge_item_to_pending(
    project_name: str,
    category: str,
    knowledge_id: str,
    *,
    reason: str = "",
) -> dict:
    target_category = str(category or "").strip()
    target_id = str(knowledge_id or "").strip()
    if target_category not in KNOWLEDGE_CATEGORIES or not target_id:
        return {"success": False, "message": "缺少有效的知识分类或知识 ID。", "pending_id": ""}

    items = load_knowledge_category(project_name, target_category)
    item_index = next((index for index, item in enumerate(items) if str(item.get("id") or "") == target_id), -1)
    if item_index < 0:
        return {"success": False, "message": "未找到要退回的正式知识。", "pending_id": ""}

    item = dict(items[item_index])
    remaining = [entry for index, entry in enumerate(items) if index != item_index]
    pending = load_pending_knowledge_items(project_name)
    existing_pending_ids = {str(entry.get("pending_id") or "") for entry in pending}
    pending_id = str(item.get("source_pending_id") or "")
    if not pending_id or pending_id in existing_pending_ids:
        pending_id = f"pending_returned_{uuid4().hex}"

    restored = dict(item)
    restored.pop("id", None)
    restored.pop("auto_reviewed_at", None)
    restored["pending_id"] = pending_id
    restored["category"] = target_category
    restored["status"] = "pending"
    restored["returned_from_knowledge_id"] = target_id
    restored["returned_from_auto_review_run_id"] = item.get("auto_review_run_id", "")
    restored["return_reason"] = reason
    restored["returned_at"] = datetime.now(timezone.utc).isoformat()
    pending.append(restored)

    save_knowledge_category(project_name, target_category, remaining)
    save_pending_knowledge_items(project_name, pending)

    run_id = str(item.get("auto_review_run_id") or "")
    if run_id:
        runs = load_auto_review_runs(project_name)
        for run in runs:
            if str(run.get("run_id") or "") != run_id:
                continue
            returned = run.get("returned_records", [])
            if not isinstance(returned, list):
                returned = []
            returned.append({
                "category": target_category,
                "knowledge_id": target_id,
                "pending_id": pending_id,
                "name": item.get("name", ""),
                "returned_at": restored["returned_at"],
                "reason": reason,
            })
            run["returned_records"] = returned
            break
        save_auto_review_runs(project_name, runs)

    sync_project_retrieval_assets(project_name)
    return {
        "success": True,
        "message": f"已将 {item.get('name', target_id)} 退回待确认队列。",
        "pending_id": pending_id,
    }


def load_story_rules(project_name: str, story_id: str) -> dict:
    path = _story_rules_overrides_path(project_name, story_id)
    if not path.exists():
        return normalize_rules(None)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return normalize_rules(raw)
    except Exception:
        return normalize_rules(None)


def save_story_rules(project_name: str, story_id: str, rules: dict):
    path = _story_rules_overrides_path(project_name, story_id)
    normalized = normalize_rules(rules)
    if all(len(v) == 0 for v in normalized.values()):
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def load_global_rules() -> dict:
    GLOBAL_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not GLOBAL_RULES_PATH.exists():
        rules = normalize_rules(None)
        save_global_rules(rules)
        return rules

    try:
        rules = json.loads(GLOBAL_RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        rules = normalize_rules(None)
        save_global_rules(rules)
        return rules
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

    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        rules = normalize_rules(None)
        save_project_rules(project_name, rules)
        return rules
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


def save_outline(project_name: str, outline: str, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "outline.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_outline(project_name: str, story_id: str = "default") -> str:
    path = _story_path_from_project_path(project_name, story_id, "outline.md")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _outline_discussion_path(project_name: str, story_id: str = "default") -> Path:
    return _story_path_from_project_path(project_name, story_id, "outline.discussion.json")


def save_outline_discussion_artifact(project_name: str, discussion: dict, report_markdown: str, story_id: str = "default"):
    path = _outline_discussion_path(project_name, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_outline_discussion_artifact(project_name: str, story_id: str = "default") -> dict:
    path = _outline_discussion_path(project_name, story_id)
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


def delete_outline_discussion_artifact(project_name: str, story_id: str = "default") -> bool:
    path = _outline_discussion_path(project_name, story_id)
    if not path.exists():
        return False
    path.unlink()
    sync_project_retrieval_assets(project_name)
    return True


def volumes_path(project_name: str, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "volumes")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _volume_markdown_path(project_name: str, volume_no: int, story_id: str = "default") -> Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.md"


def _volume_meta_path(project_name: str, volume_no: int, story_id: str = "default") -> Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.meta.json"


def _volume_discussion_path(project_name: str, volume_no: int, story_id: str = "default") -> Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.discussion.json"


def arcs_path(project_name: str, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "arcs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _arc_markdown_path(project_name: str, arc_no: int, story_id: str = "default") -> Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.md"


def _arc_meta_path(project_name: str, arc_no: int, story_id: str = "default") -> Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.meta.json"


def _arc_discussion_path(project_name: str, arc_no: int, story_id: str = "default") -> Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.discussion.json"


def _arc_chapter_plan_path(project_name: str, arc_no: int, story_id: str = "default") -> Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.chapter_plan.json"


def save_volume_outline(project_name: str, volume_no: int, outline: str, story_id: str = "default"):
    file = _volume_markdown_path(project_name, volume_no, story_id)
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_volume_outline(project_name: str, volume_no: int, story_id: str = "default") -> str:
    file = _volume_markdown_path(project_name, volume_no, story_id)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_volume_metadata(project_name: str, volume_no: int, metadata: dict, story_id: str = "default"):
    current = load_volume_metadata(project_name, volume_no, story_id)
    normalized = VolumeOutlineMetadata.model_validate({**current, **metadata, "volume_no": volume_no})
    file = _volume_meta_path(project_name, volume_no, story_id)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_volume_discussion_artifact(project_name: str, volume_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _volume_discussion_path(project_name, volume_no, story_id)
    payload = {
        "volume_no": volume_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))}, story_id)
    sync_project_retrieval_assets(project_name)


def load_volume_discussion_artifact(project_name: str, volume_no: int, story_id: str = "default") -> dict:
    file = _volume_discussion_path(project_name, volume_no, story_id)
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


def delete_volume_discussion_artifact(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    file = _volume_discussion_path(project_name, volume_no, story_id)
    if not file.exists():
        return False
    file.unlink()
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": False}, story_id)
    sync_project_retrieval_assets(project_name)
    return True


def load_volume_metadata(project_name: str, volume_no: int, story_id: str = "default") -> dict:
    file = _volume_meta_path(project_name, volume_no, story_id)
    fallback = VolumeOutlineMetadata(volume_no=volume_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return VolumeOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def list_volumes(project_name: str, story_id: str = "default") -> list[dict]:
    path = volumes_path(project_name, story_id)
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
        metadata = load_volume_metadata(project_name, volume_no, story_id)
        outline = load_volume_outline(project_name, volume_no, story_id)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_volume(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    deleted = False
    markdown_path = _volume_markdown_path(project_name, volume_no, story_id)
    meta_path = _volume_meta_path(project_name, volume_no, story_id)
    discussion_path = _volume_discussion_path(project_name, volume_no, story_id)
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
        chapter_outline_dir = _story_path_from_project_path(project_name, story_id, "chapter_outlines")
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


def save_arc_outline(project_name: str, arc_no: int, outline: str, story_id: str = "default"):
    file = _arc_markdown_path(project_name, arc_no, story_id)
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_arc_outline(project_name: str, arc_no: int, story_id: str = "default") -> str:
    file = _arc_markdown_path(project_name, arc_no, story_id)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_arc_metadata(project_name: str, arc_no: int, metadata: dict, story_id: str = "default"):
    current = load_arc_metadata(project_name, arc_no, story_id)
    normalized = ArcOutlineMetadata.model_validate({**current, **metadata, "arc_no": arc_no})
    file = _arc_meta_path(project_name, arc_no, story_id)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_arc_discussion_artifact(project_name: str, arc_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _arc_discussion_path(project_name, arc_no, story_id)
    payload = {
        "arc_no": arc_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))}, story_id)
    sync_project_retrieval_assets(project_name)


def load_arc_discussion_artifact(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    file = _arc_discussion_path(project_name, arc_no, story_id)
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


def delete_arc_discussion_artifact(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    file = _arc_discussion_path(project_name, arc_no, story_id)
    if not file.exists():
        return False
    file.unlink()
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": False}, story_id)
    sync_project_retrieval_assets(project_name)
    return True


def save_arc_chapter_plan(project_name: str, arc_no: int, plan: dict, report_markdown: str, story_id: str = "default"):
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
    payload = {
        "arc_no": arc_no,
        "plan": plan if isinstance(plan, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_arc_chapter_plan(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
    if not file.exists():
        return {}
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    plan = payload.get("plan", {})
    return {
        "arc_no": arc_no,
        "plan": plan if isinstance(plan, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_arc_chapter_plan(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
    if not file.exists():
        return False
    file.unlink()
    sync_project_retrieval_assets(project_name)
    return True


def load_arc_metadata(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    file = _arc_meta_path(project_name, arc_no, story_id)
    fallback = ArcOutlineMetadata(arc_no=arc_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return ArcOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def list_arcs(project_name: str, volume_no: int | None = None, story_id: str = "default") -> list[dict]:
    path = arcs_path(project_name, story_id)
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
        metadata = load_arc_metadata(project_name, arc_no, story_id)
        if volume_no is not None and metadata.get("volume_no") != volume_no:
            continue
        outline = load_arc_outline(project_name, arc_no, story_id)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_arc(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    deleted = False
    markdown_path = _arc_markdown_path(project_name, arc_no, story_id)
    meta_path = _arc_meta_path(project_name, arc_no, story_id)
    discussion_path = _arc_discussion_path(project_name, arc_no, story_id)
    chapter_plan_path = _arc_chapter_plan_path(project_name, arc_no, story_id)
    if markdown_path.exists():
        markdown_path.unlink()
        deleted = True
    if meta_path.exists():
        meta_path.unlink()
        deleted = True
    if discussion_path.exists():
        discussion_path.unlink()
        deleted = True
    if chapter_plan_path.exists():
        chapter_plan_path.unlink()
        deleted = True
    if deleted:
        chapter_outline_dir = _story_path_from_project_path(project_name, story_id, "chapter_outlines")
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


def _chapter_outline_meta_path(project_name: str, chapter_no: int, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.meta.json"


def _chapter_discussion_path(project_name: str, chapter_no: int, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.discussion.json"


def save_chapter_outline(project_name: str, chapter_no: int, outline: str, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(outline, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_chapter_outline_metadata(project_name: str, chapter_no: int, metadata: dict, story_id: str = "default"):
    normalized = ChapterOutlineMetadata.model_validate({**metadata, "chapter_no": chapter_no})
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id)
    file.write_text(json.dumps(normalized.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_chapter_discussion_artifact(project_name: str, chapter_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
    payload = {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default") -> dict:
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
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


def delete_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
    if not file.exists():
        return False
    file.unlink()
    sync_project_retrieval_assets(project_name)
    return True


def load_chapter_outline_metadata(project_name: str, chapter_no: int, story_id: str = "default") -> dict:
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id)
    fallback = ChapterOutlineMetadata(chapter_no=chapter_no).model_dump()
    if not file.exists():
        return fallback
    try:
        return ChapterOutlineMetadata.model_validate(json.loads(file.read_text(encoding="utf-8"))).model_dump()
    except Exception:
        return fallback


def load_chapter_outline(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _story_path_from_project_path(project_name, story_id, "chapter_outlines") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_chapter(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "chapters")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_chapter(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _story_path_from_project_path(project_name, story_id, "chapters") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_review(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "reviews")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_review(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _story_path_from_project_path(project_name, story_id, "reviews") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


DEFAULT_SUMMARY_LIMIT = 5

def get_recent_chapter_summaries(project_name: str, limit: int = DEFAULT_SUMMARY_LIMIT, story_id: str = "default") -> list[dict]:
    summaries = load_story_chapter_summaries(project_name, story_id)
    summaries = [
        item for item in summaries
        if isinstance(item, dict) and item.get("summary")
    ]
    summaries.sort(key=lambda item: item.get("chapter_no", 0))
    return summaries[-limit:]


def save_review_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "reviews")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.json"
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_review_json(project_name: str, chapter_no: int, story_id: str = "default") -> dict | None:
    file = _story_path_from_project_path(project_name, story_id, "reviews") / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_analysis_report(project_name: str, analysis_type: str, chapter_no: int, content: str, story_id: str = "default"):
    path = _story_path_from_project_path(project_name, story_id, "analysis")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_analysis_report(project_name: str, analysis_type: str, chapter_no: int, story_id: str = "default") -> str:
    file = _story_path_from_project_path(project_name, story_id, "analysis") / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def source_package_report_path(project_name: str) -> Path:
    path = project_path(project_name) / "analysis"
    path.mkdir(exist_ok=True)
    return path / "source_package.md"


def save_source_package_report(project_name: str, content: str):
    source_package_report_path(project_name).write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_source_package_report(project_name: str) -> str:
    file = source_package_report_path(project_name)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def evaluation_path(project_name: str, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "evaluation")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_evaluation_report(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def save_evaluation_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def load_evaluation_report(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def load_evaluation_json(project_name: str, chapter_no: int, story_id: str = "default") -> dict | None:
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return None


def runs_path(project_name: str, story_id: str = "default") -> Path:
    path = _story_path_from_project_path(project_name, story_id, "runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pipeline_run(project_name: str, run_id: str, content: str, story_id: str = "default"):
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    file.write_text(content, encoding="utf-8")


def load_pipeline_run(project_name: str, run_id: str, story_id: str = "default") -> str:
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def list_pipeline_runs(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[str]:
    path = runs_path(project_name, story_id)
    files = sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if chapter_no is None:
        return [file.stem for file in files]
    chapter_prefix = f"chapter_{chapter_no:03d}_"
    return [file.stem for file in files if file.stem.startswith(chapter_prefix)]


def long_reference_batches_path(project_name: str) -> Path:
    path = project_path(project_name) / "long_reference_batches"
    path.mkdir(exist_ok=True)
    return path


def long_reference_batch_path(project_name: str, batch_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_\-]+", "_", str(batch_id or "")).strip("_")
    if not safe_id:
        raise ValueError("Batch id cannot be empty.")
    return long_reference_batches_path(project_name) / f"{safe_id}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def summarize_long_reference_batch(batch: dict) -> dict:
    segments = batch.get("segments", []) if isinstance(batch.get("segments", []), list) else []
    imported_count = len([item for item in segments if item.get("import_status") == "imported"])
    extracted_count = len([item for item in segments if item.get("extract_status") in {"queued", "extracted"}])
    failed_count = len([item for item in segments if item.get("extract_status") == "failed"])
    skipped_count = len([item for item in segments if item.get("extract_status") == "skipped"])
    total_count = len(segments)
    return {
        "segment_count": total_count,
        "imported_count": imported_count,
        "extract_queued_count": extracted_count,
        "extract_failed_count": failed_count,
        "extract_skipped_count": skipped_count,
        "import_pending_count": max(total_count - imported_count, 0),
        "extract_pending_count": len([
            item for item in segments
            if item.get("extract_status", "pending") in {"pending", ""}
        ]),
    }


def normalize_long_reference_batch(batch: dict | None) -> dict:
    raw = batch if isinstance(batch, dict) else {}
    batch_id = str(raw.get("batch_id") or f"batch_{uuid4().hex}")
    now = _now_iso()
    segments = []
    for index, item in enumerate(raw.get("segments", []) if isinstance(raw.get("segments", []), list) else [], start=1):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content", ""))
        title = str(item.get("title") or f"片段 {index:03d}")
        segments.append({
            **item,
            "segment_id": str(item.get("segment_id") or f"seg_{index:04d}_{uuid4().hex[:8]}"),
            "index": int(item.get("index") or index),
            "title": title,
            "content": content,
            "char_count": int(item.get("char_count") or len(content)),
            "split_method": str(item.get("split_method") or "未知"),
            "import_status": str(item.get("import_status") or "pending"),
            "extract_status": str(item.get("extract_status") or "pending"),
            "queued_knowledge_count": int(item.get("queued_knowledge_count") or 0),
            "imported_source_name": str(item.get("imported_source_name") or ""),
            "extract_error": str(item.get("extract_error") or ""),
        })
    normalized = {
        **raw,
        "batch_id": batch_id,
        "title": str(raw.get("title") or "长篇资料批次"),
        "scope": str(raw.get("scope") or "reference"),
        "authority": str(raw.get("authority") or "curated"),
        "source_type": str(raw.get("source_type") or "external_source"),
        "source_origin": str(raw.get("source_origin") or ""),
        "source_file_name": str(raw.get("source_file_name") or ""),
        "content_fingerprint": str(raw.get("content_fingerprint") or ""),
        "content_char_count": int(raw.get("content_char_count") or sum(len(item.get("content", "")) for item in segments)),
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
        "segments": segments,
    }
    normalized["summary"] = summarize_long_reference_batch(normalized)
    return normalized


def create_long_reference_batch(
    project_name: str,
    *,
    title: str,
    scope: str,
    authority: str,
    source_type: str,
    source_origin: str = "",
    source_file_name: str = "",
    content_fingerprint: str = "",
    content_char_count: int = 0,
    segments: list[dict],
) -> dict:
    batch = normalize_long_reference_batch({
        "batch_id": f"batch_{uuid4().hex}",
        "title": title,
        "scope": scope,
        "authority": authority,
        "source_type": source_type,
        "source_origin": source_origin,
        "source_file_name": source_file_name,
        "content_fingerprint": content_fingerprint,
        "content_char_count": content_char_count,
        "segments": segments,
    })
    save_long_reference_batch(project_name, batch)
    return batch


def save_long_reference_batch(project_name: str, batch: dict) -> dict:
    normalized = normalize_long_reference_batch({
        **(batch or {}),
        "updated_at": _now_iso(),
    })
    path = long_reference_batch_path(project_name, normalized["batch_id"])
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def load_long_reference_batch(project_name: str, batch_id: str) -> dict:
    path = long_reference_batch_path(project_name, batch_id)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return normalize_long_reference_batch(raw)


def list_long_reference_batches(project_name: str) -> list[dict]:
    path = long_reference_batches_path(project_name)
    batches = []
    for file in sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            raw = json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            continue
        batch = normalize_long_reference_batch(raw)
        batch["file_name"] = file.name
        batches.append(batch)
    return batches


def delete_long_reference_batch(project_name: str, batch_id: str) -> bool:
    path = long_reference_batch_path(project_name, batch_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def retrieval_path(project_name: str) -> Path:
    path = project_path(project_name) / "retrieval"
    path.mkdir(exist_ok=True)
    return path


def retrieval_sources_path(project_name: str) -> Path:
    path = retrieval_path(project_name) / "sources"
    path.mkdir(parents=True, exist_ok=True)
    return path


def conflict_resolutions_path(project_name: str) -> Path:
    return retrieval_path(project_name) / "conflict_resolutions.json"


def retrieval_eval_cases_path(project_name: str) -> Path:
    return retrieval_path(project_name) / "eval_cases.json"


def retrieval_eval_runs_path(project_name: str) -> Path:
    return retrieval_path(project_name) / "eval_runs.json"


def retrieval_feedback_path(project_name: str) -> Path:
    return retrieval_path(project_name) / "feedback.json"


def load_conflict_resolutions(project_name: str) -> list[dict]:
    file = conflict_resolutions_path(project_name)
    if not file.exists():
        return []
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    results = []
    for item in raw:
        try:
            results.append(ConflictResolution.model_validate(item).model_dump())
        except Exception:
            continue
    return results


def save_conflict_resolution(project_name: str, resolution: dict) -> dict:
    from datetime import datetime

    normalized = ConflictResolution.model_validate({
        **resolution,
        "updated_at": str(resolution.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
    }).model_dump()
    resolutions = load_conflict_resolutions(project_name)
    resolutions = [item for item in resolutions if item.get("conflict_id") != normalized["conflict_id"]]
    resolutions.append(normalized)
    file = conflict_resolutions_path(project_name)
    file.write_text(json.dumps(resolutions, ensure_ascii=False, indent=2), encoding="utf-8")
    sync_project_retrieval_assets(project_name)
    return normalized


def _normalize_string_list_field(value) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace("，", ",").split(",") if item.strip()]
    return []


def normalize_retrieval_eval_case(case: dict) -> dict:
    payload = dict(case or {})
    now = datetime.now(timezone.utc).isoformat()
    case_id = str(payload.get("case_id") or "").strip() or f"rag_eval_{uuid4().hex}"
    top_k = payload.get("top_k", 6)
    try:
        top_k = max(1, min(20, int(top_k)))
    except (TypeError, ValueError):
        top_k = 6
    min_expected_matches = payload.get("min_expected_matches", 1)
    try:
        min_expected_matches = max(1, int(min_expected_matches))
    except (TypeError, ValueError):
        min_expected_matches = 1
    retrieval_mode = str(payload.get("retrieval_mode") or "hybrid").strip()
    if retrieval_mode not in {"hybrid", "lexical", "semantic"}:
        retrieval_mode = "hybrid"
    worldline_mode = str(payload.get("worldline_mode") or "prefer").strip()
    if worldline_mode not in {"prefer", "strict"}:
        worldline_mode = "prefer"
    return {
        "case_id": case_id,
        "name": str(payload.get("name") or payload.get("query") or "未命名评测用例").strip(),
        "query": str(payload.get("query") or "").strip(),
        "expected_terms": _normalize_string_list_field(payload.get("expected_terms", [])),
        "expected_chunk_ids": _normalize_string_list_field(payload.get("expected_chunk_ids", [])),
        "expected_source_types": _normalize_string_list_field(payload.get("expected_source_types", [])),
        "allowed_scopes": _normalize_string_list_field(payload.get("allowed_scopes", [])),
        "allowed_source_types": _normalize_string_list_field(payload.get("allowed_source_types", [])),
        "retrieval_profile": str(payload.get("retrieval_profile") or "").strip(),
        "retrieval_mode": retrieval_mode,
        "worldline_id": str(payload.get("worldline_id") or "").strip(),
        "worldline_mode": worldline_mode,
        "top_k": top_k,
        "min_expected_matches": min_expected_matches,
        "notes": str(payload.get("notes") or "").strip(),
        "status": str(payload.get("status") or "active").strip() or "active",
        "created_at": str(payload.get("created_at") or now),
        "updated_at": now,
    }


def load_retrieval_eval_cases(project_name: str) -> list[dict]:
    return _load_json_list(retrieval_eval_cases_path(project_name))


def save_retrieval_eval_cases(project_name: str, cases: list[dict]):
    normalized = [
        normalize_retrieval_eval_case(item)
        for item in (cases or [])
        if isinstance(item, dict)
    ]
    retrieval_eval_cases_path(project_name).write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_retrieval_eval_case(project_name: str, case: dict) -> dict:
    normalized = normalize_retrieval_eval_case(case)
    if not normalized["query"]:
        raise ValueError("评测查询不能为空。")
    if not (normalized["expected_terms"] or normalized["expected_chunk_ids"] or normalized["expected_source_types"]):
        raise ValueError("至少需要一个期望命中词、片段 ID 或来源类型。")
    cases = load_retrieval_eval_cases(project_name)
    updated = []
    replaced = False
    for item in cases:
        if str(item.get("case_id") or "") == normalized["case_id"]:
            normalized["created_at"] = item.get("created_at") or normalized["created_at"]
            updated.append(normalized)
            replaced = True
        else:
            updated.append(item)
    if not replaced:
        updated.append(normalized)
    save_retrieval_eval_cases(project_name, updated)
    return normalized


def delete_retrieval_eval_case(project_name: str, case_id: str) -> bool:
    target_id = str(case_id or "").strip()
    cases = load_retrieval_eval_cases(project_name)
    remaining = [item for item in cases if str(item.get("case_id") or "") != target_id]
    if len(remaining) == len(cases):
        return False
    save_retrieval_eval_cases(project_name, remaining)
    return True


def load_retrieval_eval_runs(project_name: str) -> list[dict]:
    return _load_json_list(retrieval_eval_runs_path(project_name))


def append_retrieval_eval_run(project_name: str, run: dict) -> dict:
    normalized = dict(run or {})
    normalized["run_id"] = str(normalized.get("run_id") or f"rag_eval_run_{uuid4().hex}")
    normalized["created_at"] = str(normalized.get("created_at") or datetime.now(timezone.utc).isoformat())
    runs = load_retrieval_eval_runs(project_name)
    runs.append(normalized)
    retrieval_eval_runs_path(project_name).write_text(json.dumps(runs[-200:], ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def load_retrieval_feedback(project_name: str) -> list[dict]:
    return _load_json_list(retrieval_feedback_path(project_name))


def append_retrieval_feedback(project_name: str, feedback: dict) -> dict:
    allowed_ratings = {"helpful", "priority", "irrelevant", "wrong"}
    payload = dict(feedback or {})
    rating = str(payload.get("rating") or "").strip()
    if rating not in allowed_ratings:
        raise ValueError("未知的检索反馈类型。")
    chunk_id = str(payload.get("chunk_id") or "").strip()
    if not chunk_id:
        raise ValueError("缺少检索片段 ID。")
    normalized = {
        "feedback_id": str(payload.get("feedback_id") or f"rag_feedback_{uuid4().hex}"),
        "created_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "query": str(payload.get("query") or "").strip(),
        "rating": rating,
        "note": str(payload.get("note") or "").strip(),
        "chunk_id": chunk_id,
        "document_id": str(payload.get("document_id") or "").strip(),
        "source_type": str(payload.get("source_type") or "").strip(),
        "scope": str(payload.get("scope") or "").strip(),
        "title": str(payload.get("title") or "").strip(),
        "path": str(payload.get("path") or "").strip(),
    }
    items = load_retrieval_feedback(project_name)
    items.append(normalized)
    retrieval_feedback_path(project_name).write_text(json.dumps(items[-1000:], ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


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


def chapter_count(project_name: str, story_id: str = "default") -> int:
    chapters_dir = _story_path_from_project_path(project_name, story_id, "chapters")
    if not chapters_dir.exists():
        return 0
    return len([f for f in chapters_dir.iterdir() if f.suffix == ".md"])

