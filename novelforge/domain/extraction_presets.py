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
        "categories": ["characters", "items", "abilities", "world_rules", "locations", "organizations", "timeline_events", "relationships", "writing_style", "dialogue_style", "constraints"],
    },
    "character_expert": {
        "label": "角色专家",
        "mode": "characters",
        "categories": ["characters", "dialogue_style", "relationships", "constraints", "timeline_events"],
    },
    "relationship_expert": {
        "label": "关系专家",
        "mode": "relationships",
        "categories": ["relationships", "characters", "timeline_events", "dialogue_style", "constraints"],
    },
    "timeline_expert": {
        "label": "时间线专家",
        "mode": "timeline",
        "categories": ["timeline_events", "relationships", "characters", "world_rules", "constraints"],
    },
    "world_expert": {
        "label": "设定专家",
        "mode": "world",
        "categories": ["world_rules", "locations", "organizations", "abilities", "items", "constraints"],
    },
    "style_expert": {
        "label": "文风专家",
        "mode": "style",
        "categories": ["writing_style", "dialogue_style", "narrative_techniques", "constraints"],
    },
    "canon_auditor": {
        "label": "原作审计",
        "mode": "strict_canon",
        "categories": ["characters", "relationships", "timeline_events", "world_rules", "abilities", "items", "constraints"],
    },
    "fanfic_researcher": {
        "label": "同人参考研究",
        "mode": "fanfic_reference",
        "categories": ["characters", "relationships", "writing_style", "dialogue_style", "narrative_techniques", "constraints"],
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


def default_extraction_categories(strategy: str, preset: dict, category_options: list[str]) -> list[str]:
    if strategy == "all":
        return list(category_options)
    if strategy == "none":
        return []
    return [category for category in preset.get("categories", []) if category in category_options]
