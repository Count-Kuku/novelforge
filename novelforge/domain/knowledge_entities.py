from hashlib import sha256
import re

from novelforge.domain.knowledge_quality import merge_list_values, merge_text_values, normalize_knowledge_match_name
from novelforge.domain.knowledge_workflows import safe_confidence
from novelforge.services.memory import load_entity_aliases, load_knowledge_base
from novelforge.services.memory.knowledge_center import (
    load_character_entity_cards as _load_character_entity_cards,
    load_setting_entity_cards as _load_setting_entity_cards,
)


DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"

SETTING_ENTITY_CATEGORY_GROUPS = {
    "world_rules": "世界规则",
    "locations": "地点",
    "organizations": "组织",
    "abilities": "能力体系",
    "items": "物品道具",
    "constraints": "硬性约束",
}

GLOBAL_WORLDLINE_IDS = {"", "all", "global", "shared", "common", "canon", "unknown"}


def _isolation_group_key(item: dict) -> tuple[str, str, str, str]:
    """Return the domain in which same-named facts may be merged."""

    story_id = str(item.get("story_id") or "").strip()
    setting_scope = str(item.get("setting_scope") or ("story" if story_id else "project")).strip().lower()
    if setting_scope != "story":
        story_id = ""
    worldline_id = str(item.get("worldline_id") or "").strip().lower()
    if worldline_id in GLOBAL_WORLDLINE_IDS:
        worldline_id = ""
    version_scope = str(item.get("version_scope") or "").strip().lower()
    return setting_scope, story_id, worldline_id, version_scope


def _isolation_compatible(candidate: dict, target: dict) -> bool:
    """Allow global facts into a scoped card, never a different scoped fact."""

    _, candidate_story, candidate_worldline, candidate_version = _isolation_group_key(candidate)
    _, target_story, target_worldline, target_version = _isolation_group_key(target)
    if candidate_story:
        if not target_story or candidate_story != target_story:
            return False
    if candidate_worldline:
        if not target_worldline or candidate_worldline != target_worldline:
            return False
    if candidate_version:
        if not target_version or candidate_version != target_version:
            return False
    return True


def _entity_card_id(prefix: str, category: str, normalized_name: str, item: dict) -> str:
    domain = "|".join(_isolation_group_key(item))
    digest = sha256(f"{category}|{normalized_name}|{domain}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def merge_details_values(items: list[dict]) -> dict:
    merged: dict[str, str] = {}
    for item in items:
        details = item.get("details", {})
        if not isinstance(details, dict):
            continue
        for key, value in details.items():
            cleaned_key = str(key).strip()
            cleaned_value = str(value or "").strip()
            if not cleaned_key or not cleaned_value:
                continue
            if cleaned_key in merged:
                merged[cleaned_key] = merge_text_values([merged[cleaned_key], cleaned_value])
            else:
                merged[cleaned_key] = cleaned_value
    return merged


def merge_typed_values(items: list[dict]) -> dict:
    """Merge structured fields for display while retaining source ownership."""

    merged: dict = {}
    for item in items:
        typed = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
        for key, value in typed.items():
            if value in (None, "", []):
                continue
            if isinstance(value, list):
                current = merged.get(key, [])
                merged[key] = merge_list_values([current if isinstance(current, list) else [current], value])
            elif key not in merged:
                merged[key] = value
            elif str(value) not in str(merged[key]):
                merged[key] = merge_text_values([str(merged[key]), str(value)])
    return merged


def pick_authority(values: list[str]) -> str:
    priority = {"official": 5, "project": 4, "curated": 3, "community": 2, "unknown": 1}
    cleaned = [str(value or "unknown") for value in values]
    return max(cleaned or ["unknown"], key=lambda value: priority.get(value, 0))


def build_merged_knowledge_item(category: str, selected_items: list[dict]) -> dict:
    first = selected_items[0] if selected_items else {}
    merged_name = first.get("name", "")
    summaries = [item.get("summary", "") for item in selected_items]
    source_titles = [item.get("source_title", "") for item in selected_items]
    source_origins = [item.get("source_origin", "") for item in selected_items]
    return {
        "id": first.get("id", ""),
        "category": category,
        "name": merged_name,
        "summary": merge_text_values(summaries),
        "details": merge_details_values(selected_items),
        "evidence": merge_list_values([item.get("evidence", []) for item in selected_items]),
        "confidence": max([safe_confidence(item.get("confidence", 0.7)) for item in selected_items] or [0.7]),
        "tags": merge_list_values([item.get("tags", []) for item in selected_items]),
        "scope": first.get("scope", "reference"),
        "setting_scope": first.get("setting_scope", "story" if first.get("story_id") else "project"),
        "story_id": first.get("story_id", ""),
        "worldline_id": first.get("worldline_id", ""),
        "worldline_label": first.get("worldline_label", ""),
        "version_scope": first.get("version_scope", ""),
        "canon_status": first.get("canon_status", "unknown"),
        "authority": pick_authority([item.get("authority", "unknown") for item in selected_items]),
        "source_title": merge_text_values(source_titles, separator="；"),
        "source_origin": merge_text_values(source_origins, separator="；"),
        "status": "confirmed",
        "merged_from": [item.get("id", "") for item in selected_items if item.get("id")],
    }


def item_search_text(item: dict) -> str:
    if not isinstance(item, dict):
        return ""
    parts = [
        item.get("name", ""),
        item.get("summary", ""),
        item.get("source_title", ""),
        " ".join(str(tag) for tag in item.get("tags", []) if str(tag).strip()) if isinstance(item.get("tags", []), list) else "",
    ]
    for structured in (item.get("typed_data", {}), item.get("details", {})):
        if not isinstance(structured, dict):
            continue
        parts.extend([str(key) for key in structured.keys()])
        for value in structured.values():
            if isinstance(value, list):
                parts.extend(str(entry) for entry in value)
            else:
                parts.append(str(value))
    return "\n".join(str(part) for part in parts if str(part).strip())


def related_items_for_character(character_name: str, items: list[dict], aliases: list[str] | None = None) -> list[dict]:
    match_names = [character_name] + list(aliases or [])
    normalized_names = [
        normalize_knowledge_match_name(name)
        for name in match_names
        if normalize_knowledge_match_name(name)
    ]
    if not normalized_names:
        return []
    matched = []
    for item in items:
        text = normalize_knowledge_match_name(item_search_text(item))
        if any(name in text for name in normalized_names):
            matched.append(item)
    return matched


def aliases_for_entity(alias_groups: list[dict], category: str, name: str, target_item: dict | None = None) -> list[str]:
    normalized_name = normalize_knowledge_match_name(name)
    if not normalized_name:
        return []
    aliases = []
    for group in alias_groups:
        if str(group.get("category") or "") != category:
            continue
        if target_item is not None and not _isolation_compatible(group, target_item):
            continue
        names = [group.get("canonical_name", "")] + list(group.get("aliases", []) if isinstance(group.get("aliases", []), list) else [])
        normalized_names = {normalize_knowledge_match_name(value) for value in names if normalize_knowledge_match_name(value)}
        if normalized_name not in normalized_names:
            continue
        aliases.extend([str(value).strip() for value in names if str(value).strip()])
    return merge_list_values([aliases])


def collect_character_card_sources(knowledge_base: dict, character_item: dict, alias_groups: list[dict] | None = None) -> dict[str, list[dict]]:
    name = str(character_item.get("name", "") or "").strip()
    aliases = aliases_for_entity(alias_groups or [], "characters", name, character_item)
    scoped = {
        category: [
            item for item in items
            if isinstance(item, dict) and _isolation_compatible(item, character_item)
        ]
        for category, items in knowledge_base.items()
        if isinstance(items, list)
    }
    return {
        "character_items": [character_item],
        "relationships": related_items_for_character(name, scoped.get("relationships", []), aliases),
        "abilities": related_items_for_character(name, scoped.get("abilities", []), aliases),
        "items": related_items_for_character(name, scoped.get("items", []), aliases),
        "dialogue_style": related_items_for_character(name, scoped.get("dialogue_style", []), aliases),
        "constraints": related_items_for_character(name, scoped.get("constraints", []), aliases),
        "timeline_events": related_items_for_character(name, scoped.get("timeline_events", []), aliases),
    }


def summarize_items_for_card(items: list[dict], max_items: int = 8) -> list[str]:
    lines = []
    seen = set()
    for item in items[:max_items]:
        name = str(item.get("name", "") or "").strip()
        summary = str(item.get("summary", "") or "").strip()
        text = f"{name}：{summary}" if name and summary else (summary or name)
        if not text or text in seen:
            continue
        seen.add(text)
        lines.append(text)
    return lines


def source_chips_for_items(items: list[dict], max_items: int = 12) -> list[dict]:
    """Build compact source references without copying source facts."""

    chips: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (
            str(item.get("source_title") or "").strip(),
            str(item.get("source_origin") or "").strip(),
            str(item.get("source_segment_id") or "").strip(),
        )
        if not any(key) or key in seen:
            continue
        seen.add(key)
        chips.append({
            "title": key[0] or "未命名来源",
            "origin": key[1],
            "segment_id": key[2],
            "knowledge_id": str(item.get("id") or item.get("knowledge_id") or ""),
        })
        if len(chips) >= max_items:
            break
    return chips


def timeline_item_sort_key(item: dict) -> tuple:
    """Return a deterministic creator-facing order for mixed timeline labels."""

    typed = item.get("typed_data") if isinstance(item.get("typed_data"), dict) else {}
    raw_order = str(typed.get("order_hint") or item.get("order_hint") or "").strip()
    raw_time = str(typed.get("time") or item.get("time") or "").strip()

    def natural_parts(value: str) -> tuple:
        return tuple(
            (0, int(part)) if part.isdigit() else (1, part.casefold())
            for part in re.split(r"(\d+)", value)
            if part
        )

    return (
        0 if raw_order else 1,
        natural_parts(raw_order),
        0 if raw_time else 1,
        natural_parts(raw_time),
        str(item.get("name") or "").casefold(),
        str(item.get("id") or item.get("knowledge_id") or ""),
    )


def build_character_entity_cards(project_name: str, max_characters: int = 80) -> list[dict]:
    """Entity-centric character cards (delegates to the DB-backed read path)."""
    return _load_character_entity_cards(project_name, max_characters=max_characters)


def build_setting_entity_cards(project_name: str, max_cards: int = 120) -> list[dict]:
    """Entity-centric setting cards (delegates to the DB-backed read path)."""
    return _load_setting_entity_cards(project_name, max_cards=max_cards)
