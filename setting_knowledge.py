import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from memory import (
    KNOWLEDGE_CATEGORIES,
    list_stories,
    load_knowledge_base,
    load_knowledge_category,
    load_memory,
    load_story_memory,
    save_knowledge_category,
    story_path,
    sync_project_retrieval_assets,
)


SETTING_FIELD_SPECS = {
    "canon_mode": {"category": "constraints", "label": "原作对齐方式", "scalar": True},
    "au_rules": {"category": "constraints", "label": "架空规则", "scalar": False},
    "world": {"category": "world_rules", "label": "世界观", "scalar": False},
    "characters": {"category": "characters", "label": "角色", "scalar": False},
    "relationships": {"category": "relationships", "label": "角色关系", "scalar": False},
    "timeline": {"category": "timeline_events", "label": "时间线", "scalar": False},
    "foreshadowing": {"category": "narrative_techniques", "label": "伏笔", "scalar": False},
    "active_constraints": {"category": "constraints", "label": "硬性约束", "scalar": False},
    "locations": {"category": "locations", "label": "地点资料", "scalar": False},
    "organizations": {"category": "organizations", "label": "组织资料", "scalar": False},
    "power_systems": {"category": "world_rules", "label": "能力体系", "scalar": False},
    "relationship_graph": {"category": "relationships", "label": "关系图补充", "scalar": False},
}

SETTING_CATEGORY_ORDER = [
    "characters",
    "relationships",
    "world_rules",
    "timeline_events",
    "constraints",
    "locations",
    "organizations",
    "abilities",
    "items",
    "narrative_techniques",
    "writing_style",
    "dialogue_style",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "").strip())
    return text[:48] or "default"


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("summary", "content", "description", "title", "name", "relation"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _short_name(value: str, fallback: str) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return fallback
    for separator in ["：", ":", "，", ",", "。", ".", "；", ";"]:
        if separator in text:
            head = text.split(separator, 1)[0].strip()
            if head:
                text = head
                break
    return text[:36].rstrip() or fallback


def _stable_setting_id(setting_scope: str, story_id: str, field_name: str, index: int) -> str:
    raw = f"{setting_scope}:{story_id}:{field_name}:{index}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]
    scope_part = _slug(setting_scope)
    story_part = _slug(story_id or "project")
    return f"core_{scope_part}_{story_part}_{field_name}_{index:04d}_{digest}"


def _stable_copied_setting_id(source_item: dict, target_scope: str, target_story_id: str) -> str:
    source_id = str(source_item.get("id") or source_item.get("name") or source_item.get("summary") or "")
    raw = f"{source_id}:{target_scope}:{target_story_id}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]
    return f"core_copy_{_slug(target_scope)}_{_slug(target_story_id or 'project')}_{digest}"


def _knowledge_item_index(items: list[dict]) -> dict[str, int]:
    return {
        str(item.get("id") or ""): index
        for index, item in enumerate(items)
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _normalized_identity_text(value: Any) -> str:
    return " ".join(_stringify(value).split()).casefold()


def _setting_item_identity(item: dict, setting_scope: str, story_id: str) -> str:
    scope = _normalize_scope_value(str(item.get("setting_scope") or setting_scope))
    sid = str(item.get("story_id") or story_id) if scope == "story" else ""
    parts = [
        scope,
        sid,
        str(item.get("category") or ""),
        str(item.get("setting_field") or ""),
        _normalized_identity_text(item.get("summary") or item.get("name") or ""),
    ]
    return "|".join(parts)


def _normalize_scope_value(value: str) -> str:
    normalized = str(value or "project").strip().lower()
    return "story" if normalized == "story" else "project"


def _setting_category_rank(category: str) -> int:
    try:
        return SETTING_CATEGORY_ORDER.index(category)
    except ValueError:
        return len(SETTING_CATEGORY_ORDER)


def _load_story_overrides(project_name: str, story_id: str) -> dict:
    if story_id == "default":
        return load_memory(project_name)
    path = story_path(project_name, story_id) / "memory_overrides.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def build_setting_items_from_memory(
    memory: dict,
    *,
    setting_scope: str,
    story_id: str = "",
    source_title: str = "",
) -> list[dict]:
    items: list[dict] = []
    created_at = _now()
    setting_scope = _normalize_scope_value(setting_scope)
    for field_name, spec in SETTING_FIELD_SPECS.items():
        raw_value = memory.get(field_name, "")
        values = raw_value if isinstance(raw_value, list) else ([raw_value] if raw_value else [])
        for index, value in enumerate(values, start=1):
            summary = _stringify(value)
            if not summary:
                continue
            category = str(spec["category"])
            label = str(spec["label"])
            item_id = _stable_setting_id(setting_scope, story_id, field_name, index)
            details = {"原始设定": summary, "来源字段": field_name, "设定层级": source_title or setting_scope}
            if isinstance(value, dict):
                details.update({str(key): _stringify(item) for key, item in value.items() if _stringify(item)})
            items.append({
                "id": item_id,
                "category": category,
                "name": _short_name(summary, f"{label} {index}"),
                "summary": summary,
                "details": details,
                "evidence": [{
                    "source_title": source_title or ("故事核心设定" if setting_scope == "story" else "项目核心设定"),
                    "quote": summary[:160],
                    "note": "由旧核心设定迁移为统一设定条目。",
                }],
                "confidence": 1.0,
                "importance": 0.9,
                "evidence_strength": 1.0,
                "canon_status": "user_override",
                "extraction_mode": "manual_setting",
                "tags": ["核心设定", label, field_name],
                "scope": "project",
                "authority": "project",
                "source_title": source_title or ("故事核心设定" if setting_scope == "story" else "项目核心设定"),
                "source_origin": "migration",
                "status": "confirmed",
                "setting_role": "core",
                "setting_scope": setting_scope,
                "setting_field": field_name,
                "story_id": story_id if setting_scope == "story" else "",
                "injection_policy": "always",
                "version_scope": "project_main",
                "worldline_id": "main",
                "worldline_label": "本项目主线",
                "created_at": created_at,
                "updated_at": created_at,
            })
    return items


def upsert_setting_item(project_name: str, category: str, item: dict) -> dict:
    if category not in KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    now = _now()
    normalized = dict(item or {})
    normalized["category"] = category
    normalized["id"] = str(normalized.get("id") or f"core_manual_{hashlib.md5((now + str(normalized.get('name', ''))).encode('utf-8')).hexdigest()[:12]}")
    normalized["name"] = str(normalized.get("name") or _short_name(str(normalized.get("summary") or ""), "未命名设定")).strip()
    normalized["summary"] = str(normalized.get("summary") or "").strip()
    normalized["scope"] = "project"
    normalized["authority"] = str(normalized.get("authority") or "project")
    normalized["status"] = str(normalized.get("status") or "confirmed")
    normalized["setting_role"] = str(normalized.get("setting_role") or "core")
    normalized["setting_scope"] = _normalize_scope_value(str(normalized.get("setting_scope") or "project"))
    normalized["setting_field"] = str(normalized.get("setting_field") or "")
    normalized["story_id"] = str(normalized.get("story_id") or "") if normalized["setting_scope"] == "story" else ""
    normalized["injection_policy"] = str(normalized.get("injection_policy") or "always")
    normalized["source_origin"] = str(normalized.get("source_origin") or "manual_setting")
    normalized["source_title"] = str(normalized.get("source_title") or ("故事核心设定" if normalized["setting_scope"] == "story" else "项目核心设定"))
    normalized["version_scope"] = str(normalized.get("version_scope") or "project_main")
    normalized["worldline_id"] = str(normalized.get("worldline_id") or "main")
    normalized["worldline_label"] = str(normalized.get("worldline_label") or "本项目主线")
    normalized["updated_at"] = now
    normalized.setdefault("created_at", now)
    normalized.setdefault("confidence", 1.0)
    normalized.setdefault("importance", 0.9)
    normalized.setdefault("evidence_strength", 1.0)
    normalized.setdefault("canon_status", "user_override")
    normalized.setdefault("extraction_mode", "manual_setting")
    if not isinstance(normalized.get("details"), dict):
        normalized["details"] = {}
    normalized["details"] = {str(key): _stringify(value) for key, value in normalized["details"].items() if _stringify(value)}
    normalized["details"].setdefault("原始设定", normalized["summary"])
    normalized["details"].setdefault("来源字段", normalized["setting_field"])
    if not isinstance(normalized.get("tags"), list):
        normalized["tags"] = []
    normalized["tags"] = [str(tag).strip() for tag in normalized["tags"] if str(tag).strip()]
    for tag in ["核心设定", normalized["setting_field"]]:
        if tag and tag not in normalized["tags"]:
            normalized["tags"].append(tag)
    if not isinstance(normalized.get("evidence"), list):
        normalized["evidence"] = []

    items = load_knowledge_category(project_name, category)
    index_by_id = _knowledge_item_index(items)
    existing_index = index_by_id.get(normalized["id"])
    if existing_index is None:
        items.append(normalized)
    else:
        existing = items[existing_index] if isinstance(items[existing_index], dict) else {}
        normalized["created_at"] = existing.get("created_at") or normalized["created_at"]
        items[existing_index] = normalized
    save_knowledge_category(project_name, category, items)
    sync_project_retrieval_assets(project_name)
    return normalized


def delete_setting_item(project_name: str, category: str, item_id: str) -> bool:
    if category not in KNOWLEDGE_CATEGORIES:
        return False
    target_id = str(item_id or "").strip()
    if not target_id:
        return False
    items = load_knowledge_category(project_name, category)
    remaining = [item for item in items if str(item.get("id") or "") != target_id]
    if len(remaining) == len(items):
        return False
    save_knowledge_category(project_name, category, remaining)
    sync_project_retrieval_assets(project_name)
    return True


def delete_story_setting_items(project_name: str, story_id: str) -> dict:
    target_story_id = str(story_id or "").strip()
    if not target_story_id:
        return {"deleted": 0, "categories": []}
    deleted = 0
    changed_categories: list[str] = []
    for category in KNOWLEDGE_CATEGORIES:
        items = load_knowledge_category(project_name, category)
        remaining = []
        removed_here = 0
        for item in items:
            if (
                isinstance(item, dict)
                and _normalize_scope_value(str(item.get("setting_scope") or "project")) == "story"
                and str(item.get("story_id") or "").strip() == target_story_id
            ):
                removed_here += 1
                continue
            remaining.append(item)
        if removed_here:
            save_knowledge_category(project_name, category, remaining)
            deleted += removed_here
            changed_categories.append(category)
    if changed_categories:
        sync_project_retrieval_assets(project_name)
    return {"deleted": deleted, "categories": changed_categories}


def _select_source_setting_items(project_name: str, source_scope: str, source_story_id: str) -> list[dict]:
    source_scope = _normalize_scope_value(source_scope)
    items = list_setting_items(project_name, source_story_id or "default", core_only=True)
    selected: list[dict] = []
    for item in items:
        item_scope = _normalize_scope_value(str(item.get("setting_scope") or "project"))
        item_story_id = str(item.get("story_id") or "")
        if source_scope == "project" and item_scope == "project":
            selected.append(item)
        elif source_scope == "story" and item_scope == "story" and item_story_id == source_story_id:
            selected.append(item)
    return selected


def _clone_setting_item(
    item: dict,
    *,
    target_scope: str,
    target_story_id: str,
    source_label: str,
) -> dict:
    now = _now()
    target_scope = _normalize_scope_value(target_scope)
    source_id = str(item.get("id") or "")
    clone = dict(item)
    clone["id"] = _stable_copied_setting_id(item, target_scope, target_story_id)
    clone["setting_scope"] = target_scope
    clone["story_id"] = target_story_id if target_scope == "story" else ""
    clone["setting_role"] = str(clone.get("setting_role") or "core")
    clone["injection_policy"] = str(clone.get("injection_policy") or "always")
    clone["scope"] = "project"
    clone["authority"] = "project"
    clone["status"] = "confirmed"
    clone["source_origin"] = "setting_copy"
    clone["source_title"] = source_label
    clone["copied_from_setting_id"] = source_id
    clone["copied_from_setting_scope"] = str(item.get("setting_scope") or "project")
    clone["copied_from_story_id"] = str(item.get("story_id") or "")
    clone["copied_at"] = now
    clone["updated_at"] = now
    clone.setdefault("created_at", now)
    details = clone.get("details") if isinstance(clone.get("details"), dict) else {}
    clone["details"] = {
        **details,
        "复制来源": source_label,
        "复制来源设定ID": source_id,
    }
    tags = [str(tag).strip() for tag in clone.get("tags", []) if str(tag).strip()] if isinstance(clone.get("tags"), list) else []
    for tag in ["核心设定", "复制设定"]:
        if tag not in tags:
            tags.append(tag)
    clone["tags"] = tags
    return clone


def copy_setting_items(
    project_name: str,
    *,
    source_scope: str,
    source_story_id: str = "",
    target_scope: str,
    target_story_id: str = "",
    source_label: str = "",
) -> dict:
    source_scope = _normalize_scope_value(source_scope)
    target_scope = _normalize_scope_value(target_scope)
    source_story_id = str(source_story_id or "")
    target_story_id = str(target_story_id or "")
    if source_scope == target_scope and (source_scope != "story" or source_story_id == target_story_id):
        return {"copied": 0, "updated": 0, "skipped": 0, "source_count": 0}

    selected = _select_source_setting_items(project_name, source_scope, source_story_id)
    copied = 0
    updated = 0
    skipped = 0
    changed_categories: set[str] = set()
    for item in selected:
        category = str(item.get("category") or "")
        if category not in KNOWLEDGE_CATEGORIES:
            skipped += 1
            continue
        clone = _clone_setting_item(
            item,
            target_scope=target_scope,
            target_story_id=target_story_id,
            source_label=source_label or str(item.get("source_title") or "核心设定复制"),
        )
        existing = load_knowledge_category(project_name, category)
        index_by_id = _knowledge_item_index(existing)
        target_index = index_by_id.get(str(clone.get("id") or ""))
        if target_index is None:
            clone_identity = _setting_item_identity(clone, target_scope, target_story_id)
            for index, existing_item in enumerate(existing):
                if not isinstance(existing_item, dict):
                    continue
                if _setting_item_identity(existing_item, target_scope, target_story_id) == clone_identity:
                    target_index = index
                    clone["id"] = str(existing_item.get("id") or clone.get("id") or "")
                    break

        if target_index is None:
            existing.append(clone)
            copied += 1
        else:
            previous = existing[target_index] if isinstance(existing[target_index], dict) else {}
            clone["created_at"] = previous.get("created_at") or clone.get("created_at")
            existing[target_index] = {**previous, **clone}
            updated += 1
        save_knowledge_category(project_name, category, existing)
        changed_categories.add(category)

    if changed_categories:
        sync_project_retrieval_assets(project_name)
    return {
        "copied": copied,
        "updated": updated,
        "skipped": skipped,
        "source_count": len(selected),
        "categories": sorted(changed_categories),
    }


def copy_project_core_settings_to_story(project_name: str, target_story_id: str) -> dict:
    return copy_setting_items(
        project_name,
        source_scope="project",
        target_scope="story",
        target_story_id=target_story_id,
        source_label="项目核心设定",
    )


def copy_story_core_settings_to_project(project_name: str, source_story_id: str) -> dict:
    return copy_setting_items(
        project_name,
        source_scope="story",
        source_story_id=source_story_id,
        target_scope="project",
        source_label=f"故事核心设定：{source_story_id}",
    )


def copy_story_core_settings_to_story(project_name: str, source_story_id: str, target_story_id: str) -> dict:
    return copy_setting_items(
        project_name,
        source_scope="story",
        source_story_id=source_story_id,
        target_scope="story",
        target_story_id=target_story_id,
        source_label=f"故事核心设定：{source_story_id}",
    )


def migrate_core_settings_to_knowledge(project_name: str, story_id: str | None = None) -> dict:
    sources: list[tuple[dict, str, str, str]] = [(load_memory(project_name), "project", "", "项目核心设定")]
    if story_id is None:
        story_ids = [str(story.get("story_id") or "default") for story in list_stories(project_name)]
    else:
        story_ids = [story_id]
    for sid in story_ids:
        if sid == "default":
            continue
        overrides = _load_story_overrides(project_name, sid)
        if overrides:
            sources.append((overrides, "story", sid, f"故事核心设定：{sid}"))

    migrated = 0
    updated = 0
    for memory, setting_scope, sid, source_title in sources:
        items = build_setting_items_from_memory(
            memory,
            setting_scope=setting_scope,
            story_id=sid,
            source_title=source_title,
        )
        grouped: dict[str, list[dict]] = {}
        for item in items:
            grouped.setdefault(str(item["category"]), []).append(item)
        for category, category_items in grouped.items():
            existing = load_knowledge_category(project_name, category)
            index_by_id = _knowledge_item_index(existing)
            changed = False
            for item in category_items:
                existing_index = index_by_id.get(str(item["id"]))
                if existing_index is None:
                    existing.append(item)
                    index_by_id[str(item["id"])] = len(existing) - 1
                    migrated += 1
                    changed = True
                else:
                    original = existing[existing_index] if isinstance(existing[existing_index], dict) else {}
                    merged = {**original, **item, "created_at": original.get("created_at") or item.get("created_at")}
                    if merged != original:
                        existing[existing_index] = merged
                        updated += 1
                        changed = True
            if changed:
                save_knowledge_category(project_name, category, existing)
    return {"migrated": migrated, "updated": updated}


def list_setting_items(project_name: str, story_id: str = "default", *, core_only: bool = True) -> list[dict]:
    rows: list[dict] = []
    knowledge_base = load_knowledge_base(project_name)
    for category, items in knowledge_base.items():
        for item in items:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or "confirmed")
            if status != "confirmed":
                continue
            setting_role = str(item.get("setting_role") or "")
            injection_policy = str(item.get("injection_policy") or "")
            if core_only and setting_role != "core" and injection_policy != "always":
                continue
            setting_scope = str(item.get("setting_scope") or "project")
            item_story_id = str(item.get("story_id") or "")
            if setting_scope == "story" and item_story_id != story_id:
                continue
            row = dict(item)
            row["category"] = category
            rows.append(row)
    rows.sort(key=lambda item: (
        0 if str(item.get("setting_scope") or "project") == "story" else 1,
        _setting_category_rank(str(item.get("category") or "")),
        str(item.get("setting_field") or ""),
        str(item.get("name") or ""),
    ))
    return rows


def group_setting_items_by_field(items: list[dict]) -> dict[str, list[dict]]:
    grouped = {field: [] for field in SETTING_FIELD_SPECS}
    for item in items:
        field_name = str(item.get("setting_field") or "")
        if field_name in grouped:
            grouped[field_name].append(item)
    return grouped


def build_generation_setting_context(project_name: str, story_id: str = "default") -> dict:
    memory = load_story_memory(project_name, story_id)
    items = list_setting_items(project_name, story_id, core_only=True)
    grouped = group_setting_items_by_field(items)
    for field_name, field_items in grouped.items():
        if not field_items:
            continue
        summaries = [str(item.get("summary") or "").strip() for item in field_items if str(item.get("summary") or "").strip()]
        if not summaries:
            continue
        if SETTING_FIELD_SPECS[field_name].get("scalar"):
            memory[field_name] = summaries[0]
        else:
            memory[field_name] = summaries
    memory["_setting_context"] = format_setting_items_for_prompt(items)
    return memory


def format_setting_items_for_prompt(items: list[dict]) -> str:
    if not items:
        return ""
    grouped: dict[str, list[str]] = {}
    for item in items:
        field_name = str(item.get("setting_field") or "")
        label = SETTING_FIELD_SPECS.get(field_name, {}).get("label") or item.get("category") or "设定"
        summary = str(item.get("summary") or "").strip()
        if summary:
            grouped.setdefault(str(label), []).append(summary)
    lines: list[str] = []
    for label, values in grouped.items():
        lines.append(f"### {label}")
        lines.extend(f"- {value}" for value in values)
        lines.append("")
    return "\n".join(lines).strip()
