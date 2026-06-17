from knowledge_quality import merge_list_values, merge_text_values, normalize_knowledge_match_name
from knowledge_workflows import safe_confidence
from memory import load_entity_aliases, load_knowledge_base


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
    details = item.get("details", {})
    if isinstance(details, dict):
        parts.extend([str(key) for key in details.keys()])
        parts.extend([str(value) for value in details.values()])
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


def aliases_for_entity(alias_groups: list[dict], category: str, name: str) -> list[str]:
    normalized_name = normalize_knowledge_match_name(name)
    if not normalized_name:
        return []
    aliases = []
    for group in alias_groups:
        if str(group.get("category") or "") != category:
            continue
        names = [group.get("canonical_name", "")] + list(group.get("aliases", []) if isinstance(group.get("aliases", []), list) else [])
        normalized_names = {normalize_knowledge_match_name(value) for value in names if normalize_knowledge_match_name(value)}
        if normalized_name not in normalized_names:
            continue
        aliases.extend([str(value).strip() for value in names if str(value).strip()])
    return merge_list_values([aliases])


def collect_character_card_sources(knowledge_base: dict, character_item: dict, alias_groups: list[dict] | None = None) -> dict[str, list[dict]]:
    name = str(character_item.get("name", "") or "").strip()
    aliases = aliases_for_entity(alias_groups or [], "characters", name)
    return {
        "character_items": [character_item],
        "relationships": related_items_for_character(name, knowledge_base.get("relationships", []), aliases),
        "abilities": related_items_for_character(name, knowledge_base.get("abilities", []), aliases),
        "items": related_items_for_character(name, knowledge_base.get("items", []), aliases),
        "dialogue_style": related_items_for_character(name, knowledge_base.get("dialogue_style", []), aliases),
        "constraints": related_items_for_character(name, knowledge_base.get("constraints", []), aliases),
        "timeline_events": related_items_for_character(name, knowledge_base.get("timeline_events", []), aliases),
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


def build_character_entity_cards(project_name: str, max_characters: int = 80) -> list[dict]:
    knowledge_base = load_knowledge_base(project_name)
    alias_groups = load_entity_aliases(project_name)
    character_items = [
        item for item in knowledge_base.get("characters", [])
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]
    grouped: dict[str, list[dict]] = {}
    for item in character_items:
        key = normalize_knowledge_match_name(item.get("name", ""))
        if not key:
            continue
        grouped.setdefault(key, []).append(item)

    cards = []
    for index, (_, items) in enumerate(grouped.items(), start=1):
        if len(cards) >= max_characters:
            break
        primary = items[0]
        name = str(primary.get("name", "") or f"角色 {index}").strip()
        merged_character = build_merged_knowledge_item("characters", items)
        aliases = aliases_for_entity(alias_groups, "characters", name)
        sources = collect_character_card_sources(knowledge_base, primary, alias_groups)
        related_relationships = summarize_items_for_card(sources["relationships"])
        related_abilities = summarize_items_for_card(sources["abilities"] + sources["items"])
        dialogue_notes = summarize_items_for_card(sources["dialogue_style"], max_items=5)
        constraints = summarize_items_for_card(sources["constraints"], max_items=5)
        timeline = summarize_items_for_card(sources["timeline_events"], max_items=6)
        evidence = merge_list_values([
            item.get("evidence", []) for source_items in sources.values() for item in source_items
        ])[:8]
        source_ids = merge_list_values([
            [item.get("id", "") for source_items in sources.values() for item in source_items if item.get("id")]
        ])
        tags = merge_list_values([merged_character.get("tags", []), ["角色实体卡", "entity_character"]])
        card = {
            "id": f"character_entity_{index:04d}",
            "entity_type": "character",
            "name": name,
            "aliases": aliases,
            "summary": merged_character.get("summary", ""),
            "profile": merged_character.get("details", {}),
            "relationships": related_relationships,
            "abilities_and_items": related_abilities,
            "dialogue_style": dialogue_notes,
            "constraints": constraints,
            "timeline": timeline,
            "evidence": evidence,
            "confidence": merged_character.get("confidence", 0.7),
            "importance": max([safe_confidence(item.get("importance", 0.5)) for item in items] or [0.5]),
            "canon_status": primary.get("canon_status", "unknown"),
            "source_knowledge_ids": source_ids,
            "tags": tags,
            "status": "entity_card",
        }
        cards.append(card)
    return cards


def build_setting_entity_cards(project_name: str, max_cards: int = 120) -> list[dict]:
    knowledge = load_knowledge_base(project_name)
    cards = []
    source_categories = ["world_rules", "locations", "organizations", "abilities", "items", "constraints"]
    index = 1
    for category in source_categories:
        items = [item for item in knowledge.get(category, []) if isinstance(item, dict)]
        groups: dict[str, list[dict]] = {}
        for item in items:
            name_key = normalize_knowledge_match_name(item.get("name", ""))
            if not name_key:
                continue
            groups.setdefault(name_key, []).append(item)
        for _, group_items in sorted(groups.items(), key=lambda pair: -max(safe_confidence(item.get("importance", 0.5)) for item in pair[1])):
            primary = sorted(
                group_items,
                key=lambda item: (
                    -safe_confidence(item.get("importance", 0.5)),
                    -safe_confidence(item.get("evidence_strength", 0.5)),
                    -safe_confidence(item.get("confidence", 0.7)),
                ),
            )[0]
            related_timeline = related_items_for_character(primary.get("name", ""), knowledge.get("timeline_events", []), [])[:6]
            related_relationships = related_items_for_character(primary.get("name", ""), knowledge.get("relationships", []), [])[:6]
            details = primary.get("details", {}) if isinstance(primary.get("details", {}), dict) else {}
            evidence = merge_list_values([item.get("evidence", []) for item in group_items])[:8]
            card = {
                "id": f"setting_entity_{index:04d}",
                "entity_type": "setting",
                "setting_type": category,
                "name": primary.get("name", "未命名设定"),
                "summary": merge_text_values([item.get("summary", "") for item in group_items])[:1200],
                "profile": details,
                "rules": summarize_items_for_card(group_items, max_items=8),
                "timeline": summarize_items_for_card(related_timeline, max_items=6),
                "related_entities": summarize_items_for_card(related_relationships, max_items=6),
                "evidence": evidence,
                "confidence": primary.get("confidence", 0.7),
                "importance": max([safe_confidence(item.get("importance", 0.5)) for item in group_items] or [0.5]),
                "canon_status": primary.get("canon_status", "unknown"),
                "version_scope": primary.get("version_scope", "unknown"),
                "worldline_id": primary.get("worldline_id", DEFAULT_WORLDLINE_ID),
                "worldline_label": primary.get("worldline_label", DEFAULT_WORLDLINE_LABEL),
                "source_knowledge_ids": merge_list_values([[item.get("id", "") for item in group_items if item.get("id")]]),
                "tags": merge_list_values([[SETTING_ENTITY_CATEGORY_GROUPS.get(category, category), "设定实体卡", "entity_setting"], primary.get("tags", [])]),
                "status": "entity_card",
            }
            cards.append(card)
            index += 1
            if len(cards) >= max_cards:
                return cards
    return cards
