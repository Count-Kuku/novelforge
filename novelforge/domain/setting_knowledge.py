import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from novelforge.domain.knowledge_entities import GLOBAL_WORLDLINE_IDS, worldline_allowed

from novelforge.services.memory import (
    delete_knowledge_category_item_record,
    KNOWLEDGE_CATEGORIES,
    list_stories,
    load_creative_profile,
    load_knowledge_base,
    load_knowledge_category,
    load_memory,
    load_story_memory,
    load_story_memory_overrides,
    merge_worldline_baseline,
    save_knowledge_category,
    sync_project_retrieval_assets,
    upsert_knowledge_category_item_record,
)


SETTING_FIELD_SPECS = {
    # canon_mode 是 story memory 的一等字段（core.py:216），由 prompt 直接读取，
    # 不再作为知识条目单存（Entity-Fact-Relation 重构后移除）。
    "au_rules": {"category": "world_rules", "label": "架空规则", "scalar": False},
    "world": {"category": "world_rules", "label": "世界观", "scalar": False},
    "characters": {"category": "characters", "label": "角色", "scalar": False},
    "relationships": {"category": "relationships", "label": "角色关系", "scalar": False},
    "timeline": {"category": "timeline_events", "label": "时间线", "scalar": False},
    "foreshadowing": {"category": "narrative_techniques", "label": "伏笔", "scalar": False},
    "active_constraints": {"category": "world_rules", "label": "硬性约束", "scalar": False},
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
    "locations",
    "organizations",
    "abilities",
    "items",
    "narrative_techniques",
    "writing_style",
    "dialogue_style",
]

INJECTION_POLICIES = {"always", "retrieval", "manual_only"}
# 权威定义与 strict 判定实现在 `domain/knowledge_entities`（曾在本模块、retrieval/common
# 各存一份，改一处会漏两处）。此处 re-export 保持既有 `from ...setting_knowledge import
# GLOBAL_WORLDLINE_IDS` 调用方不受影响。

# Upper bound for the always-injection setting block (L0 constant layer).
# Keeps the hard-constraint block from growing without bound as chapters
# accumulate; the most important items (by importance) win.
ALWAYS_INJECTION_LIMIT = 40


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


def normalize_injection_policy(value: str | None, *, default: str = "always") -> str:
    fallback = str(default or "always").strip().lower()
    if fallback not in INJECTION_POLICIES:
        fallback = "always"
    normalized = str(value or fallback).strip().lower()
    return normalized if normalized in INJECTION_POLICIES else fallback


def _setting_worldline_allowed(item: dict, worldline_id: str | None, worldline_mode: str) -> bool:
    return worldline_allowed(item.get("worldline_id"), worldline_id, worldline_mode)


def _setting_category_rank(category: str) -> int:
    try:
        return SETTING_CATEGORY_ORDER.index(category)
    except ValueError:
        return len(SETTING_CATEGORY_ORDER)


def _load_story_overrides(project_name: str, story_id: str) -> dict:
    if story_id == "default":
        return load_memory(project_name)
    return load_story_memory_overrides(project_name, story_id)


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
                    "source_title": source_title or ("故事优先设定" if setting_scope == "story" else "项目优先设定"),
                    "quote": summary[:160],
                    "note": "由旧版设定迁移为统一优先设定条目。",
                }],
                "confidence": 1.0,
                "importance": 0.9,
                "evidence_strength": 1.0,
                "canon_status": "user_override",
                "extraction_mode": "manual_setting",
                "tags": ["优先设定", label, field_name],
                "scope": "project",
                "authority": "project",
                "source_title": source_title or ("故事优先设定" if setting_scope == "story" else "项目优先设定"),
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
    normalized["injection_policy"] = normalize_injection_policy(normalized.get("injection_policy"))
    normalized["source_origin"] = str(normalized.get("source_origin") or "manual_setting")
    normalized["source_title"] = str(normalized.get("source_title") or ("故事优先设定" if normalized["setting_scope"] == "story" else "项目优先设定"))
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
    for tag in ["优先设定", normalized["setting_field"]]:
        if tag and tag not in normalized["tags"]:
            normalized["tags"].append(tag)
    if not isinstance(normalized.get("evidence"), list):
        normalized["evidence"] = []

    return upsert_knowledge_category_item_record(project_name, category, normalized)


def delete_setting_item(project_name: str, category: str, item_id: str) -> bool:
    if category not in KNOWLEDGE_CATEGORIES:
        return False
    target_id = str(item_id or "").strip()
    if not target_id:
        return False
    return delete_knowledge_category_item_record(project_name, category, target_id)


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
    clone["injection_policy"] = normalize_injection_policy(clone.get("injection_policy"))
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
    for tag in ["优先设定", "复制设定"]:
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
            source_label=source_label or str(item.get("source_title") or "优先设定复制"),
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
        source_label="项目优先设定",
    )


def copy_story_core_settings_to_project(project_name: str, source_story_id: str) -> dict:
    return copy_setting_items(
        project_name,
        source_scope="story",
        source_story_id=source_story_id,
        target_scope="project",
        source_label=f"故事优先设定：{source_story_id}",
    )


def copy_story_core_settings_to_story(project_name: str, source_story_id: str, target_story_id: str) -> dict:
    return copy_setting_items(
        project_name,
        source_scope="story",
        source_story_id=source_story_id,
        target_scope="story",
        target_story_id=target_story_id,
        source_label=f"故事优先设定：{source_story_id}",
    )


def migrate_core_settings_to_knowledge(project_name: str, story_id: str | None = None) -> dict:
    sources: list[tuple[dict, str, str, str]] = [(load_memory(project_name), "project", "", "项目优先设定")]
    if story_id is None:
        story_ids = [str(story.get("story_id") or "default") for story in list_stories(project_name)]
    else:
        story_ids = [story_id]
    for sid in story_ids:
        if sid == "default":
            continue
        overrides = _load_story_overrides(project_name, sid)
        if overrides:
            sources.append((overrides, "story", sid, f"故事优先设定：{sid}"))

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


def list_setting_items(
    project_name: str,
    story_id: str = "default",
    *,
    core_only: bool = True,
    injection_policies: set[str] | None = None,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    limit: int | None = None,
    chapter_no: int | None = None,
) -> list[dict]:
    allowed_policies = (
        {normalize_injection_policy(value) for value in injection_policies}
        if injection_policies is not None
        else None
    )
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
            injection_policy = normalize_injection_policy(
                item.get("injection_policy"),
                default="always" if setting_role == "core" else "retrieval",
            )
            if core_only and setting_role != "core" and injection_policy != "always":
                continue
            if allowed_policies is not None and injection_policy not in allowed_policies:
                continue
            setting_scope = str(item.get("setting_scope") or "project")
            item_story_id = str(item.get("story_id") or "")
            if setting_scope == "story" and item_story_id != story_id:
                continue
            if not _setting_worldline_allowed(item, worldline_id, worldline_mode):
                continue
            if chapter_no is not None:
                valid_to = item.get("valid_to_chapter")
                if isinstance(valid_to, (int, float)) and valid_to <= chapter_no:
                    continue  # superseded before this chapter — skip stale fact
            row = dict(item)
            row["category"] = category
            row["injection_policy"] = injection_policy
            rows.append(row)
    rows.sort(key=lambda item: (
        0 if str(item.get("setting_scope") or "project") == "story" else 1,
        _setting_category_rank(str(item.get("category") or "")),
        str(item.get("setting_field") or ""),
        str(item.get("name") or ""),
    ))
    if limit is not None:
        # Cap the always-injection block. Importance first, then the stable sort
        # above as a tiebreak, so a large knowledge base cannot inflate the
        # hard-constraint block without bound（重要度优先截断的注入配额）。
        rows.sort(key=lambda item: (
            -(item.get("importance") if isinstance(item.get("importance"), (int, float)) else 0),
        ))
        rows = rows[: max(int(limit), 0)]
    return rows


def group_setting_items_by_field(items: list[dict]) -> dict[str, list[dict]]:
    grouped = {field: [] for field in SETTING_FIELD_SPECS}
    for item in items:
        field_name = str(item.get("setting_field") or "")
        if field_name in grouped:
            grouped[field_name].append(item)
    return grouped


def _merged_effective_items(
    project_name: str,
    story_id: str,
    *,
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    chapter_no: int | None = None,
    entity_names: set[str] | None = None,
) -> list[dict]:
    """P0/P1：经 `merge_worldline_baseline` 取「跨 canon/story 叠加 + 章号过滤」的有效设定行。

    每个 group 的 facts 展开为平铺行，`fact_key` 映射回 `setting_field`。返回行的字段对齐
    `list_setting_items` 消费方所需的 subset：`summary/category/setting_field/importance/
    injection_policy/setting_role`。replace 槽位已由 merge 取最新一条，注入不再出现矛盾值。
    `entity_names` 非空时只保留 canonical_name 命中集合的实体组（P1 实体聚焦取数）。
    """
    merged = merge_worldline_baseline(
        project_name,
        story_id=story_id,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        chapter_no=chapter_no,
    )
    wanted = set(str(item).strip() for item in entity_names) if entity_names else None
    rows: list[dict] = []
    for group in merged:
        if not isinstance(group, dict):
            continue
        if wanted is not None and str(group.get("canonical_name") or "") not in wanted:
            continue
        canonical = str(group.get("canonical_name") or "")
        for fact in group.get("facts") or []:
            if not isinstance(fact, dict):
                continue
            row = dict(fact)
            row["setting_field"] = str(fact.get("fact_key") or "")
            row["canonical_name"] = canonical
            rows.append(row)
    return rows


def _valid_start(row: dict) -> int:
    value = row.get("valid_from_chapter")
    return int(value) if isinstance(value, (int, float)) else 0


def _valid_end(row: dict) -> int | None:
    value = row.get("valid_to_chapter")
    return int(value) if isinstance(value, (int, float)) else None


def validate_temporal_conflicts(rows: list[dict]) -> list[str]:
    """P2：纯规则时序矛盾校验器（无需 LLM）。

    对每一 (canonical_name, setting_field) 槽位按生效起点排序，检测 replace 语义下
    前后两条的区间是否重叠/倒挂（前一条仍未关闭就开后一条），返回人类可读警告。

    正常 supersede 写入后区间是半开 [from, to)（前条 valid_to == 后条 valid_from），
    不会误报；只有 valid_from/valid_to 被标错（重叠/倒挂）时才触发。
    """
    warnings: list[str] = []
    buckets: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        canonical = str(row.get("canonical_name") or "").strip()
        field = str(row.get("setting_field") or "").strip()
        if not canonical or not field:
            continue
        buckets.setdefault((canonical, field), []).append(row)
    for (canonical, field), items in buckets.items():
        ordered = sorted(items, key=lambda row: (_valid_start(row), str(row.get("knowledge_id") or "")))
        for index in range(1, len(ordered)):
            previous = ordered[index - 1]
            current = ordered[index]
            prev_start = _valid_start(previous)
            curr_start = _valid_start(current)
            if curr_start < prev_start:
                warnings.append(f"时序倒挂：{canonical} 的 {field} 生效起点倒挂（{curr_start} 早于 {prev_start}）")
                continue
            prev_end = _valid_end(previous)
            if prev_end is not None and prev_end > curr_start:
                warnings.append(
                    f"时序重叠：{canonical} 的 {field} 前一条(至第{prev_end}章)未关闭即开启第{curr_start}章新值"
                )
    return warnings


def build_generation_setting_context(
    project_name: str,
    story_id: str = "default",
    *,
    chapter_no: int | None = None,
    worldline_override: str | None = None,
) -> dict:
    try:
        profile = load_creative_profile(project_name, story_id) or {}
    except Exception:
        profile = {}
    # P2（D6）：worldline 来源可被章节/arc 级元数据覆盖（worldline_override），否则回退 profile。
    worldline_id = str(worldline_override) if worldline_override else str(profile.get("worldline_id") or "")
    worldline_mode = str(profile.get("worldline_retrieval_mode") or "prefer")
    memory = load_story_memory(project_name, story_id)

    merged_rows = _merged_effective_items(
        project_name,
        story_id,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        chapter_no=chapter_no,
    )
    if merged_rows:
        # 实体+世界线视图优先：跨 scope 叠加 + 章号过滤，消除同槽位矛盾值（D3/P0）。
        structured_items = [
            item for item in merged_rows
            if str(item.get("setting_role") or "") == "core"
        ]
        # 与原 list_setting_items(core_only=True, injection_policies={"always"}) 语义一致：
        # 保留所有 injection_policy=always 的行（含 supplemental 等非 core 的 always 条目）。
        items = [
            item for item in merged_rows
            if normalize_injection_policy(item.get("injection_policy")) == "always"
        ]
        items.sort(key=lambda item: -(
            item.get("importance") if isinstance(item.get("importance"), (int, float)) else 0
        ))
        items = items[: ALWAYS_INJECTION_LIMIT]
    else:
        # 回退：实体视图为空（旧库未回填 entity_id / DB 不可用）时退回全量过滤路径，
        # 保证 always 注入不因重构而空掉。
        structured_items = [
            item
            for item in list_setting_items(project_name, story_id, core_only=True, chapter_no=chapter_no)
            if str(item.get("setting_role") or "") == "core"
        ]
        items = list_setting_items(
            project_name,
            story_id,
            core_only=True,
            injection_policies={"always"},
            worldline_id=worldline_id,
            worldline_mode=worldline_mode,
            limit=ALWAYS_INJECTION_LIMIT,
            chapter_no=chapter_no,
        )
    structured_fields = {
        str(item.get("setting_field") or "")
        for item in structured_items
        if str(item.get("setting_field") or "") in SETTING_FIELD_SPECS
    }
    if structured_fields:
        for field_name in structured_fields:
            spec = SETTING_FIELD_SPECS[field_name]
            memory[field_name] = "" if spec.get("scalar") else []
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
    # 内部契约键（refactor 2 P0）：让 context_assembly 免做第二次全量 list_setting_items。
    # 前缀下划线 + 已知键名，消费方只读，不做结构化 field，向后兼容。
    memory["_setting_structured_fields"] = sorted(
        str(item.get("setting_field") or "")
        for item in structured_items
        if str(item.get("setting_field") or "") in SETTING_FIELD_SPECS
    )
    memory["_setting_knowledge_ids"] = sorted({
        str(item.get("knowledge_id") or item.get("id") or "")
        for item in items
        if str(item.get("knowledge_id") or item.get("id") or "")
    })
    return memory


def build_entity_scoped_setting_context(
    project_name: str,
    story_id: str,
    *,
    canonical_names: list[str],
    worldline_id: str | None = None,
    worldline_mode: str = "prefer",
    chapter_no: int | None = None,
    concise: bool = False,
) -> dict:
    """P1：按「本章实体清单」聚焦 always 注入块。

    与 `build_generation_setting_context` 同构但只保留 `canonical_names` 命中实体的
    有效事实（跨 canon/story 叠加 + 章号过滤），把上下文预算从「全实体」收窄到
    「本次写作真正需要的实体」。返回 `{text, ids, items}`。

    `concise=True`（遗留 #8 收口，G15）：细纲等「中观结构」层只取每个实体的
    「清单 + 概要」——每实体至多 2 条、摘要截断到 140 字，而非完整事实。
    """
    rows = _merged_effective_items(
        project_name,
        story_id,
        worldline_id=worldline_id,
        worldline_mode=worldline_mode,
        chapter_no=chapter_no,
        entity_names=set(str(name) for name in canonical_names if str(name)),
    )
    items = [
        item for item in rows
        if normalize_injection_policy(item.get("injection_policy")) == "always"
    ]
    items.sort(key=lambda item: -(
        item.get("importance") if isinstance(item.get("importance"), (int, float)) else 0
    ))
    if concise:
        # 细纲层：清单级概要。每实体至多保留 2 条最高 importance 事实，单条摘要截断。
        per_entity_kept: dict[str, int] = {}
        concise_items: list[dict] = []
        for item in items:
            entity_key = str(item.get("canonical_name") or item.get("name") or "")
            if not entity_key:
                continue
            kept = per_entity_kept.get(entity_key, 0)
            if kept >= 2:
                continue
            per_entity_kept[entity_key] = kept + 1
            clipped = dict(item)
            summary = str(clipped.get("summary") or "").strip()
            clipped["summary"] = summary[:140] + ("…" if len(summary) > 140 else "")
            concise_items.append(clipped)
        items = concise_items
    items = items[: ALWAYS_INJECTION_LIMIT]
    return {
        "text": format_setting_items_for_prompt(items),
        "ids": sorted({
            str(item.get("knowledge_id") or item.get("id") or "")
            for item in items
            if str(item.get("knowledge_id") or item.get("id") or "")
        }),
        "items": items,
    }


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
