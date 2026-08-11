"""Typed knowledge schemas shared by ingestion, storage and management UI."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class KnowledgeField:
    key: str
    label: str
    kind: str = "text"
    aliases: tuple[str, ...] = ()
    required: bool = False


COMMON_FIELDS = (
    KnowledgeField("aliases", "别名/称呼", "list", ("alias", "别名", "称呼")),
)

KNOWLEDGE_TYPE_FIELDS: dict[str, tuple[KnowledgeField, ...]] = {
    "characters": COMMON_FIELDS + (
        KnowledgeField("roles", "身份/角色", "list", ("role", "身份", "角色")),
        KnowledgeField("appearance", "外貌", aliases=("外貌", "appearance")),
        KnowledgeField("personality", "性格", aliases=("性格", "personality")),
        KnowledgeField("motivations", "目标/动机", "list", ("目标", "动机", "motivation")),
        KnowledgeField("abilities", "能力", "list", ("能力", "技能")),
        KnowledgeField("affiliations", "所属组织", "list", ("组织", "阵营", "affiliation")),
    ),
    "items": (
        KnowledgeField("item_type", "道具类型", aliases=("类型", "item_type")),
        KnowledgeField("owners", "持有者", "list", ("owner", "持有者", "主人")),
        KnowledgeField("functions", "功能/效果", "list", ("功能", "效果", "function"), True),
        KnowledgeField("limitations", "限制", "list", ("限制", "代价", "limitation")),
        KnowledgeField("status", "当前状态", aliases=("状态", "status")),
    ),
    "abilities": (
        KnowledgeField("ability_type", "能力类型", aliases=("类型", "ability_type")),
        KnowledgeField("users", "使用者", "list", ("user", "使用者", "拥有者")),
        KnowledgeField("effects", "效果", "list", ("效果", "effect"), True),
        KnowledgeField("costs", "代价", "list", ("代价", "消耗", "cost")),
        KnowledgeField("limits", "限制/弱点", "list", ("限制", "弱点", "limit")),
    ),
    "world_rules": (
        KnowledgeField("domain", "规则领域", aliases=("领域", "domain")),
        KnowledgeField("rule", "规则正文", aliases=("规则", "rule"), required=True),
        KnowledgeField("conditions", "生效条件", "list", ("条件", "condition")),
        KnowledgeField("exceptions", "例外", "list", ("例外", "exception")),
        KnowledgeField("consequences", "后果", "list", ("后果", "consequence")),
    ),
    "locations": COMMON_FIELDS + (
        KnowledgeField("location_type", "地点类型", aliases=("类型", "location_type")),
        KnowledgeField("parent_location", "上级地点", aliases=("上级地点", "隶属", "parent")),
        KnowledgeField("features", "特征", "list", ("特征", "features")),
        KnowledgeField("inhabitants", "相关人物/居民", "list", ("居民", "人物", "inhabitants")),
    ),
    "organizations": COMMON_FIELDS + (
        KnowledgeField("organization_type", "组织类型", aliases=("类型", "organization_type")),
        KnowledgeField("leaders", "领导者", "list", ("领导", "首领", "leader")),
        KnowledgeField("members", "成员", "list", ("成员", "member")),
        KnowledgeField("goals", "目标", "list", ("目标", "宗旨", "goal")),
        KnowledgeField("relations", "组织关系", "list", ("关系", "relation")),
    ),
    "timeline_events": (
        KnowledgeField("time", "时间", aliases=("时间", "日期", "time")),
        KnowledgeField("participants", "参与者", "list", ("参与者", "人物", "participants")),
        KnowledgeField("locations", "发生地点", "list", ("地点", "locations")),
        KnowledgeField("causes", "起因", "list", ("起因", "原因", "cause")),
        KnowledgeField("outcomes", "结果/影响", "list", ("结果", "影响", "outcome")),
        KnowledgeField("order_hint", "顺序标记", aliases=("顺序", "order")),
    ),
    "relationships": (
        KnowledgeField("subject", "主体", aliases=("主体", "source", "from"), required=True),
        KnowledgeField("object", "客体", aliases=("客体", "target", "to"), required=True),
        KnowledgeField("relation_type", "关系类型", aliases=("关系", "类型", "relation_type"), required=True),
        KnowledgeField("direction", "方向", aliases=("方向", "direction")),
        KnowledgeField("status", "关系状态", aliases=("状态", "status")),
    ),
    "writing_style": (
        KnowledgeField("features", "文风特征", "list", ("特征", "features"), True),
        KnowledgeField("rhythm", "节奏", aliases=("节奏", "rhythm")),
        KnowledgeField("imagery", "意象/修辞", "list", ("意象", "修辞", "imagery")),
        KnowledgeField("avoid", "避免事项", "list", ("避免", "禁忌", "avoid")),
    ),
    "dialogue_style": (
        KnowledgeField("speaker", "适用角色", aliases=("角色", "speaker")),
        KnowledgeField("features", "对白特征", "list", ("特征", "features"), True),
        KnowledgeField("catchphrases", "口癖/常用语", "list", ("口癖", "常用语", "catchphrase")),
        KnowledgeField("avoid", "避免表达", "list", ("避免", "avoid")),
    ),
    "narrative_techniques": (
        KnowledgeField("technique", "叙事技法", aliases=("技法", "technique"), required=True),
        KnowledgeField("purpose", "作用", aliases=("作用", "目的", "purpose")),
        KnowledgeField("conditions", "使用条件", "list", ("条件", "condition")),
        KnowledgeField("examples", "例证", "list", ("例证", "示例", "example")),
    ),
    "constraints": (
        KnowledgeField("constraint_type", "约束类型", aliases=("类型", "constraint_type")),
        KnowledgeField("rule", "约束正文", aliases=("规则", "约束", "rule"), required=True),
        KnowledgeField("applies_to", "适用范围", "list", ("范围", "适用", "applies_to")),
        KnowledgeField("severity", "严格程度", aliases=("严格程度", "severity")),
        KnowledgeField("exceptions", "例外", "list", ("例外", "exception")),
    ),
}


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, (tuple, set)):
        values = list(value)
    elif isinstance(value, str):
        values = value.replace("；", "\n").replace(";", "\n").replace("、", "\n").splitlines()
    elif value is None:
        values = []
    else:
        values = [value]
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip(" \t-•")
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return result


def _find_value(item: dict, details: dict, field: KnowledgeField) -> Any:
    candidates = (field.key, *field.aliases)
    lowered = {str(key).strip().lower(): value for key, value in details.items()}
    for key in candidates:
        if key in item and item.get(key) not in (None, "", []):
            return item.get(key)
        value = lowered.get(str(key).strip().lower())
        if value not in (None, "", []):
            return value
    return None


def normalize_typed_knowledge_item(item: dict, category: str | None = None) -> dict:
    normalized = dict(item or {})
    clean_category = str(category or normalized.get("category") or "").strip()
    normalized["category"] = clean_category
    details = normalized.get("details") if isinstance(normalized.get("details"), dict) else {}
    existing = normalized.get("typed_data") if isinstance(normalized.get("typed_data"), dict) else {}
    typed_data = dict(existing)
    for field in KNOWLEDGE_TYPE_FIELDS.get(clean_category, ()):
        # An explicit typed value, including an empty value entered to clear a
        # field, wins over legacy aliases in ``details``.  Otherwise cleared
        # form fields would silently reappear on the next save.
        value = existing[field.key] if field.key in existing else _find_value(normalized, details, field)
        if field.kind == "list":
            parsed = _as_list(value)
            if parsed:
                typed_data[field.key] = parsed
        elif value not in (None, ""):
            typed_data[field.key] = str(value).strip()
    normalized["typed_data"] = typed_data
    normalized["schema_version"] = 2
    return normalized


def validate_typed_knowledge_item(item: dict, category: str | None = None) -> list[str]:
    normalized = normalize_typed_knowledge_item(item, category)
    clean_category = str(category or normalized.get("category") or "")
    typed_data = normalized.get("typed_data", {})
    return [
        f"缺少必填字段：{field.label}"
        for field in KNOWLEDGE_TYPE_FIELDS.get(clean_category, ())
        if field.required and typed_data.get(field.key) in (None, "", [])
    ]
