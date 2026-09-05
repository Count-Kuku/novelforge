from enum import Enum


KNOWLEDGE_EXTRACTION_MODE_LABELS = {
    "general": "通用提取",
    "deep": "深度提取",
    "characters": "角色专用",
    "relationships": "关系专用",
    "timeline": "时间线专用",
    "world": "设定专用",
    "style": "文风专用",
    "strict_canon": "严格原作",
    "fanfic_reference": "同人参考",
}

KNOWLEDGE_EXTRACTION_MODE_HELP = {
    "general": "均衡抽取主要角色、设定、事件、关系、物品能力、地点组织、文风和约束。适合第一次试跑或资料类型不明确的片段，输出通常更克制。",
    "deep": "面向同人写作地基的深入抽取，会更积极地保留长期可复用信息。适合正式整理原作正文，但可能产生更多需要人工审核的候选条目。",
    "characters": "优先抽取角色身份、性格、动机、底线、口癖、称呼和稳定互动模式。",
    "relationships": "优先抽取角色之间的亲密、冲突、权力、依赖、误解、保护、利用、师徒、阵营等关系。",
    "timeline": "优先抽取事件、因果、时间顺序、前置条件、后续影响和角色状态变化。",
    "world": "优先抽取世界规则、组织制度、地点、阵营、能力体系、物品限制和不能违背的设定边界。",
    "style": "优先抽取叙事视角、句式节奏、氛围、描写偏好、对白风格和场景推进方式。",
    "strict_canon": "只抽取原文明确支持、后续同人不能轻易违背的事实、关系、事件和硬性约束。",
    "fanfic_reference": "抽取对改写有帮助的角色感觉、关系张力、文风氛围、可复用桥段和可改写边界。",
}

KNOWLEDGE_EXTRACTION_EXPERT_PRESETS = {
    "balanced": {
        "label": "平衡总管",
        "mode": "deep",
        "categories": ["characters", "items", "abilities", "world_rules", "locations", "organizations", "timeline_events", "relationships", "writing_style", "dialogue_style"],
    },
    "character_expert": {
        "label": "角色专家",
        "mode": "characters",
        "categories": ["characters", "dialogue_style", "relationships", "timeline_events"],
    },
    "relationship_expert": {
        "label": "关系专家",
        "mode": "relationships",
        "categories": ["relationships", "characters", "timeline_events", "dialogue_style"],
    },
    "timeline_expert": {
        "label": "时间线专家",
        "mode": "timeline",
        "categories": ["timeline_events", "relationships", "characters", "world_rules"],
    },
    "world_expert": {
        "label": "设定专家",
        "mode": "world",
        "categories": ["world_rules", "locations", "organizations", "abilities", "items"],
    },
    "style_expert": {
        "label": "文风专家",
        "mode": "style",
        "categories": ["writing_style", "dialogue_style", "narrative_techniques"],
    },
    "canon_auditor": {
        "label": "原作审计",
        "mode": "strict_canon",
        "categories": ["characters", "relationships", "timeline_events", "world_rules", "abilities", "items"],
    },
    "fanfic_researcher": {
        "label": "同人参考研究",
        "mode": "fanfic_reference",
        "categories": ["characters", "relationships", "writing_style", "dialogue_style", "narrative_techniques"],
    },
}

KNOWLEDGE_EXTRACTION_PLAN_PRESETS = {
    "fanfic_foundation": {
        "label": "同人地基全流程",
        "steps": ["character_expert", "relationship_expert", "timeline_expert", "world_expert", "canon_auditor"],
    },
    "character_relationship": {
        "label": "角色关系优先",
        "steps": ["character_expert", "relationship_expert", "style_expert"],
    },
    "character_world": {
        "label": "图鉴（角色+世界设定）",
        "steps": ["character_expert", "world_expert"],
    },
    "world_timeline": {
        "label": "设定时间线优先",
        "steps": ["world_expert", "timeline_expert", "canon_auditor"],
    },
    "style_reference": {
        "label": "文风参考优先",
        "steps": ["style_expert", "fanfic_researcher"],
    },
    "strict_canon_audit": {
        "label": "严格原作审计",
        "steps": ["canon_auditor", "character_expert", "relationship_expert", "timeline_expert"],
    },
    "custom": {
        "label": "自定义计划",
        "steps": ["character_expert", "relationship_expert", "timeline_expert"],
    },
}

KNOWLEDGE_CONSOLIDATION_MODE_LABELS = {
    "balanced": "平衡整理",
    "character_cards": "角色卡优先",
    "timeline": "时间线优先",
    "strict_canon": "严格原作",
    "style": "文风优先",
}


class MaterialType(str, Enum):
    """外部资料的资料类型，驱动「资料类型 → 提取预设」路由（D6/A'期）。"""
    CANON = "canon"            # 原著：出时间线 + 严格原作审计
    REFERENCE = "reference"    # 图鉴/设定参考：出独立条目（角色+世界）
    BALANCED = "balanced"      # 类型不明确：均衡提取


# material_type → preset 名（计划预设为多 pass，专家预设为单 pass）。
# 消费方先查 KNOWLEDGE_EXTRACTION_PLAN_PRESETS，再回退 KNOWLEDGE_EXTRACTION_EXPERT_PRESETS。
MATERIAL_TYPE_PRESET_MAP: dict[str, str] = {
    MaterialType.CANON.value: "world_timeline",       # world→timeline→canon_auditor
    MaterialType.REFERENCE.value: "character_world",  # character_expert→world_expert
    MaterialType.BALANCED.value: "balanced",          # 专家预设（单 pass）
}


def resolve_preset_for_material(material_type: str | None) -> tuple[list[str], str]:
    """解析 material_type → (categories, mode)，用于单 pass 提取（D6/A'期）。

    计划预设（多 pass）在当前单 pass 任务模型下取第一步专家预设；
    完整多 pass 串行/并行子抽取属后续增强（D2）。
    """
    name = MATERIAL_TYPE_PRESET_MAP.get(material_type or MaterialType.BALANCED.value, "balanced")
    if name in KNOWLEDGE_EXTRACTION_EXPERT_PRESETS:
        preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS[name]
        return list(preset.get("categories", [])), str(preset.get("mode", "general"))
    plan = KNOWLEDGE_EXTRACTION_PLAN_PRESETS.get(name)
    if plan and plan.get("steps"):
        # 计划预设（多 pass）：单 pass 模型下合并各步的 categories（取并集），
        # mode 取第一步专家预设的 mode。
        categories: list[str] = []
        mode = "general"
        for idx, step in enumerate(plan["steps"]):
            preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS.get(step)
            if not preset:
                continue
            if idx == 0:
                mode = str(preset.get("mode", "general"))
            for category in preset.get("categories", []):
                if category not in categories:
                    categories.append(category)
        return categories, mode
    preset = KNOWLEDGE_EXTRACTION_EXPERT_PRESETS["balanced"]
    return list(preset.get("categories", [])), str(preset.get("mode", "general"))


def default_extraction_categories(strategy: str, preset: dict, category_options: list[str]) -> list[str]:
    if strategy == "all":
        return list(category_options)
    if strategy == "none":
        return []
    return [category for category in preset.get("categories", []) if category in category_options]
