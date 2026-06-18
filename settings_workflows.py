import json


CORE_SETTING_KNOWLEDGE_FIELDS = {
    "canon_mode": ("constraints", "原作对齐方式"),
    "au_rules": ("constraints", "架空规则"),
    "world": ("world_rules", "世界观"),
    "characters": ("characters", "角色"),
    "relationships": ("relationships", "角色关系"),
    "timeline": ("timeline_events", "时间线"),
    "foreshadowing": ("narrative_techniques", "伏笔"),
    "active_constraints": ("constraints", "硬性约束"),
    "locations": ("locations", "地点"),
    "organizations": ("organizations", "组织"),
    "power_systems": ("world_rules", "能力体系"),
    "relationship_graph": ("relationships", "关系图"),
}


def short_knowledge_name(text: str, fallback: str) -> str:
    cleaned = " ".join(str(text or "").split())
    if not cleaned:
        return fallback
    for separator in ["：", ":", "，", ",", "。", ".", "；", ";"]:
        if separator in cleaned:
            head = cleaned.split(separator, 1)[0].strip()
            if head:
                cleaned = head
                break
    return cleaned[:36].rstrip() or fallback


def build_core_setting_knowledge_items(memory: dict, source_title: str, selected_fields: list[str]) -> list[dict]:
    items: list[dict] = []
    for field_name in selected_fields:
        if field_name not in CORE_SETTING_KNOWLEDGE_FIELDS:
            continue
        category, label = CORE_SETTING_KNOWLEDGE_FIELDS[field_name]
        raw_value = memory.get(field_name, "")
        values = raw_value if isinstance(raw_value, list) else ([raw_value] if raw_value else [])
        for index, value in enumerate(values, start=1):
            if isinstance(value, dict):
                summary = json.dumps(value, ensure_ascii=False)
                name_seed = value.get("name") or value.get("title") or value.get("source") or value.get("relation") or summary
                details = {str(key): str(item) for key, item in value.items() if str(item).strip()}
            else:
                summary = str(value or "").strip()
                name_seed = summary
                details = {"原始设定": summary}
            if not summary:
                continue
            items.append({
                "category": category,
                "name": short_knowledge_name(str(name_seed), f"{label} {index}"),
                "summary": summary,
                "details": {
                    **details,
                    "来源字段": field_name,
                    "设定层级": source_title,
                },
                "evidence": [{
                    "source_title": source_title,
                    "quote": summary[:160],
                    "note": "由核心设定转入结构化知识库，便于长期检索和跨故事复用。",
                }],
                "confidence": 1.0,
                "importance": 0.8,
                "evidence_strength": 1.0,
                "canon_status": "user_override",
                "extraction_mode": "core_setting",
                "tags": ["核心设定", label, field_name],
            })
    return items
