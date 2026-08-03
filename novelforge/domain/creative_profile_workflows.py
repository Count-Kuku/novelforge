STORY_MODE_WORKFLOWS = {
    "主线故事": ["需求确认", "故事结构", "章节计划", "正文生成", "评估修订"],
    "短篇": ["需求确认", "短篇结构", "正文生成", "快速评估"],
    "中篇": ["需求确认", "故事大纲", "章节计划", "正文生成", "评估修订"],
    "长篇": ["需求确认", "全书大纲", "分卷", "剧情段", "章节细纲", "正文", "审阅与设定更新"],
    "番外": ["角色状态", "场景目标", "正文生成", "风格检查"],
    "续写": ["已有剧情状态", "伏笔与约束检查", "下一段/下一章计划", "正文生成", "连续性审阅"],
    "前传": ["目标时间点", "原设边界", "前传结构", "正文生成", "时间线检查"],
    "穿越": ["原角色核心", "新环境规则", "适配规则", "新故事结构", "正文生成"],
    "补完": ["资料缺口", "原设边界", "补完结构", "正文生成", "一致性检查"],
    "片段": ["场景目标", "角色状态", "片段正文", "快速润色"],
}

CUSTOM_OPTION_LABEL = "自定义"
DEFAULT_WORLDLINE_ID = "main"
DEFAULT_WORLDLINE_LABEL = "本项目主线"


def recommended_workflow_for_profile(profile: dict) -> list[str]:
    story_mode = str(profile.get("story_mode", "") or "")
    target_length = str(profile.get("target_length", "") or "")
    if story_mode == "主线故事":
        if "长篇" in target_length or "长" in target_length:
            return STORY_MODE_WORKFLOWS["长篇"]
        if "中篇" in target_length or "中" in target_length:
            return STORY_MODE_WORKFLOWS["中篇"]
        if "短篇" in target_length or "短" in target_length:
            return STORY_MODE_WORKFLOWS["短篇"]
        if "片段" in target_length or "场景" in target_length:
            return STORY_MODE_WORKFLOWS["片段"]
        return STORY_MODE_WORKFLOWS["主线故事"]
    if story_mode in STORY_MODE_WORKFLOWS:
        return STORY_MODE_WORKFLOWS[story_mode]

    combined = f"{story_mode} {target_length}"
    keyword_map = [
        (("续写",), "续写"),
        (("前传",), "前传"),
        (("穿越", "转生", "异世界", "平行世界", "AU", "架空"), "穿越"),
        (("番外",), "番外"),
        (("补完", "补全", "补设定"), "补完"),
        (("片段", "场景"), "片段"),
        (("短篇", "短"), "短篇"),
        (("中篇", "中"), "中篇"),
        (("长篇", "长"), "长篇"),
    ]
    for keywords, workflow_key in keyword_map:
        if any(keyword in combined for keyword in keywords):
            return STORY_MODE_WORKFLOWS[workflow_key]
    return STORY_MODE_WORKFLOWS["主线故事"]


def normalize_creative_form_state(profile: dict | None) -> dict:
    payload = dict(profile or {})
    existing_focus = payload.get("reference_focus", []) if isinstance(payload.get("reference_focus", []), list) else []
    focus_options = ["角色", "世界观", "剧情事件", "道具能力", "时间线", "写作风格", "对白风格", "写作手法", "硬性约束"]
    preset_focus = [item for item in existing_focus if item in focus_options]
    custom_focus = [item for item in existing_focus if item not in focus_options]
    return {
        "story_mode": payload.get("story_mode", "主线故事"),
        "target_length": payload.get("target_length", "长篇"),
        "target_word_count": payload.get("target_word_count", ""),
        "workflow_depth": payload.get("workflow_depth", "完整长篇流程"),
        "reference_strength": payload.get("reference_strength", "中参考"),
        "conflict_policy": payload.get("conflict_policy", "优先项目设定"),
        "allow_canon_deviation": bool(payload.get("allow_canon_deviation", True)),
        "worldline_id": payload.get("worldline_id", DEFAULT_WORLDLINE_ID),
        "worldline_label": payload.get("worldline_label", DEFAULT_WORLDLINE_LABEL),
        "worldline_retrieval_mode": payload.get("worldline_retrieval_mode", "prefer") if payload.get("worldline_retrieval_mode", "prefer") in {"prefer", "strict"} else "prefer",
        "reference_focus": preset_focus or ["角色", "世界观", "剧情事件"],
        "custom_reference_focus": "，".join(custom_focus),
    }


def build_creative_profile_from_form_values(
    story_mode: str,
    target_length: str,
    target_word_count: str,
    workflow_depth: str,
    reference_strength: str,
    conflict_policy: str,
    reference_focus: list[str],
    custom_reference_focus: str,
    allow_canon_deviation: bool,
    worldline_id: str,
    worldline_label: str,
    worldline_retrieval_mode: str,
) -> dict:
    custom_focus_items = [
        item.strip()
        for item in str(custom_reference_focus or "").replace("，", ",").split(",")
        if item.strip()
    ]
    merged_reference_focus = []
    seen_focus = set()
    for item in list(reference_focus or []) + custom_focus_items:
        if item in seen_focus:
            continue
        seen_focus.add(item)
        merged_reference_focus.append(item)
    return {
        "story_mode": story_mode,
        "target_length": target_length,
        "target_word_count": target_word_count,
        "workflow_depth": workflow_depth,
        "reference_strength": reference_strength,
        "reference_focus": merged_reference_focus,
        "allow_canon_deviation": allow_canon_deviation,
        "conflict_policy": conflict_policy,
        "worldline_id": str(worldline_id or "").strip() or DEFAULT_WORLDLINE_ID,
        "worldline_label": str(worldline_label or "").strip() or DEFAULT_WORLDLINE_LABEL,
        "worldline_retrieval_mode": worldline_retrieval_mode if worldline_retrieval_mode in {"prefer", "strict"} else "prefer",
    }


def build_profile_from_task_wizard(
    task_type: str,
    target_length: str,
    output_goal: str,
    reference_strength: str,
    target_word_count: str,
    focus_items: list[str],
    allow_canon_deviation: bool,
    conflict_policy: str,
) -> dict:
    workflow_depth = "按创作配置"
    if output_goal == "只要正文":
        workflow_depth = "只生成正文"
    elif output_goal == "短篇结构和正文":
        workflow_depth = "短篇结构+正文"
    elif output_goal == "章节计划和正文":
        workflow_depth = "章节计划+正文"
    elif output_goal == "分卷/剧情段/章节计划":
        workflow_depth = "分卷/剧情段/章节"
    elif output_goal == "完整长篇流程":
        workflow_depth = "完整长篇流程"
    elif target_length in {"片段", "短篇"}:
        workflow_depth = "短篇结构+正文"
    elif target_length == "中篇":
        workflow_depth = "章节计划+正文"
    else:
        workflow_depth = "完整长篇流程"

    return {
        "story_mode": task_type,
        "target_length": target_length,
        "target_word_count": target_word_count,
        "workflow_depth": workflow_depth,
        "reference_strength": reference_strength,
        "reference_focus": focus_items,
        "allow_canon_deviation": allow_canon_deviation,
        "conflict_policy": conflict_policy,
    }
