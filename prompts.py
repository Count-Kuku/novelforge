RULE_LABELS = {
    "all": "通用规则",
    "outline": "大纲生成规则",
    "chapter_outline": "章节细纲规则",
    "write": "正文写作规则",
    "review": "章节审阅规则",
    "memory_update": "设定更新规则",
}


def format_story_state_guidance(memory: dict) -> str:
    canon_mode = memory.get("canon_mode", "")
    au_rules = memory.get("au_rules", [])
    relationships = memory.get("relationships", [])
    active_constraints = memory.get("active_constraints", [])
    return f"""
故事状态说明：
1. `canon_mode`：{canon_mode or '未设置'}
2. `au_rules`：{au_rules or '无'}
3. `relationships`：{relationships or '无'}
4. `active_constraints`：{active_constraints or '无'}
"""


def format_discussion_history(messages: list[dict]) -> str:
    if not messages:
        return "暂无历史对话。"

    lines = []
    for item in messages:
        role = str(item.get("role", "assistant") or "assistant").strip().lower()
        content = str(item.get("content", "") or "").strip()
        if not content:
            continue
        label = "用户" if role == "user" else "讨论助手"
        lines.append(f"{label}：{content}")
    return "\n\n".join(lines) or "暂无历史对话。"


def format_rules_for_prompt(global_rules: dict, project_rules: dict, scope: str, story_rules: dict | None = None) -> str:
    lines = []

    rule_sections = [
        ("全局通用规则", global_rules.get("all", [])),
        ("项目通用规则", project_rules.get("all", [])),
        (f"全局{RULE_LABELS.get(scope, scope)}", global_rules.get(scope, [])),
        (f"项目{RULE_LABELS.get(scope, scope)}", project_rules.get(scope, [])),
    ]
    if story_rules:
        rule_sections.append((f"故事{RULE_LABELS.get(scope, scope)}", story_rules.get(scope, [])))
        if story_rules.get("all"):
            rule_sections.append(("故事通用规则", story_rules.get("all", [])))

    for label, rules in rule_sections:
        cleaned = [str(item).strip() for item in rules if str(item).strip()]
        if not cleaned:
            continue
        lines.append(f"{label}：")
        lines.extend([f"- {item}" for item in cleaned])

    if not lines:
        return "当前无额外规则。"
    return "\n".join(lines)


def outline_prompt(memory: dict, user_idea: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是一个网络小说主编，擅长同人小说、长篇规划、爽点设计。

规则约束：
{rules_text}

当前小说设定：
{memory}

{format_story_state_guidance(memory)}

用户想法：
{user_idea}

请生成一个全书大纲，包含：
1. 故事定位
2. 主线冲突
3. 主角成长线
4. 主要角色关系
5. 分卷规划
6. 前20章大致剧情
"""


def discuss_outline_prompt(memory: dict, user_idea: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是长篇小说大纲讨论 Agent。

规则约束：
{rules_text}

当前小说设定：
{memory}

{format_story_state_guidance(memory)}

用户想法：
{user_idea}

请先不要直接输出最终大纲，而是生成一个讨论式规划结果，帮助用户把全书方向讨论清楚。输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "全书大纲讨论",
  "current_understanding": "",
  "core_goals": [],
  "key_constraints": [],
  "options": [
    {{
      "title": "",
      "summary": "",
      "strengths": [],
      "risks": []
    }}
  ],
  "open_questions": [],
  "risks": [],
  "recommended_direction": "",
  "approval_ready": false
}}

要求：
1. 先明确你对用户意图的理解
2. 提出 2-3 个可执行的大纲方向或切入策略
3. 对每个方向说明优点、风险和适用条件
4. 列出还需要用户确认的关键问题
5. 如果当前信息已经足够，也要明确给出推荐方向和 approval_ready=true
"""


def discuss_creative_profile_prompt(memory: dict, current_profile: dict, user_idea: str, rules_text: str = "当前无额外规则。", retrieval_context: str = "") -> str:
    base = f"""
你是同人小说创作配置讨论 Agent。

你的目标不是直接写正文或大纲，而是帮助用户把模糊的创作想法收敛成可执行的项目创作配置。

规则约束：
{rules_text}

当前小说设定：
{memory}

{format_story_state_guidance(memory)}

当前创作配置：
{current_profile}

用户想法：
{user_idea}

请先不要直接输出最终正文/大纲，而是生成一个讨论式创作配置结果，帮助用户确认任务性质、篇幅、生成层级和资料参考策略。输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "创作配置讨论",
  "current_understanding": "",
  "key_constraints": [],
  "options": [
    {{
      "title": "",
      "summary": "",
      "strengths": [],
      "risks": []
    }}
  ],
  "open_questions": [],
  "risks": [],
  "recommended_direction": "",
  "recommended_profile": {{
    "story_mode": "",
    "target_length": "",
    "target_word_count": "",
    "workflow_depth": "",
    "reference_strength": "",
    "reference_focus": [],
    "allow_canon_deviation": true,
    "conflict_policy": "",
    "notes": ""
  }},
  "approval_ready": false
}}

要求：
1. 明确你对用户当前创作意图的理解
2. 提出 2-3 个可执行的创作配置方向或取舍方案
3. 说明每个方案更适合的任务类型、资料参考强度和工作流深度
4. `recommended_profile` 必须尽量填写完整，且字段值应适合作为当前项目配置直接保存
5. 如果某些字段还不确定，可以给出保守推荐，但必须在 `open_questions` 中说明
6. 如果当前信息已经足够，请给出推荐方向并标明 approval_ready=true
7. 请参考下方补充检索上下文中已上传的资料、知识库内容，来评估合适的参考强度、参考焦点和冲突策略
"""
    return merge_retrieval_context(base, retrieval_context)


def volume_outline_prompt(
    memory: dict,
    story_outline: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    approved_discussion_context: str,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是长篇小说分卷规划 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划分卷。'}

当前要规划第 {volume_no} 卷。

分卷标题：
{volume_title or '未命名分卷'}

分卷摘要：
{volume_summary or '暂无分卷摘要。'}

已批准讨论结论：
{approved_discussion_context or '当前分卷暂无已批准讨论结论。'}

用户要求：
{user_requirement or '用户未提供额外要求，请优先补全该分卷在全书中的功能与推进。'}

请生成该分卷大纲，至少包含：
1. 本卷定位与叙事功能
2. 本卷阶段目标
3. 本卷主冲突与次冲突
4. 关键角色推进
5. 关键事件节点
6. 节奏分段
7. 章节范围建议或预计篇幅
8. 卷末钩子与承上启下

要求补充：
1. 必须与全书大纲保持一致
2. 明确说明本卷承接上卷和通向下卷的作用
3. 如果用户要求与现有全书方向冲突，给出折中处理方式
4. 如果存在已批准讨论结论，优先遵守其中明确的本卷目标、结构重心与约束条件
5. 尽量让结果可直接作为后续剧情段规划和章节规划的上游依据
"""


def discuss_volume_prompt(
    memory: dict,
    story_outline: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是分卷规划讨论 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求讨论该分卷方向。'}

当前要讨论第 {volume_no} 卷。

分卷标题：
{volume_title or '未命名分卷'}

分卷摘要：
{volume_summary or '暂无分卷摘要。'}

用户要求：
{user_requirement or '用户暂未补充分卷要求，请优先讨论该卷在全书中的定位。'}

请先不要直接输出最终分卷大纲，而是生成一个讨论式规划结果，帮助用户确认本卷方向。输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "分卷讨论",
  "volume_goal": "",
  "current_understanding": "",
  "key_constraints": [],
  "options": [
    {{
      "title": "",
      "summary": "",
      "strengths": [],
      "risks": []
    }}
  ],
  "open_questions": [],
  "risks": [],
  "recommended_direction": "",
  "approval_ready": false
}}

要求：
1. 明确本卷在全书中的叙事功能、阶段目标和主要推进任务
2. 提出 2-3 个可执行的分卷方向或结构方案
3. 说明每个方案的节奏、优势、风险和适用条件
4. 列出仍需用户确认的关键问题
5. 如果信息已经足够，请给出推荐方向并标明 approval_ready=true
"""


def merge_retrieval_context(prompt: str, retrieval_context: str) -> str:
    if not retrieval_context.strip() or retrieval_context.strip() == "未检索到额外上下文。":
        return prompt
    return f"""{prompt}

补充检索上下文：
{retrieval_context}
"""

def chapter_outline_prompt(
    memory: dict,
    outline: str,
    volume_outline: str,
    arc_outline: str,
    volume_discussion_context: str,
    arc_discussion_context: str,
    chapter_discussion_context: str,
    recent_summaries: list[dict],
    chapter_no: int,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    recent_summary_text = "\n".join(
        [f"- 第{item.get('chapter_no', '?')}章：{item.get('summary', '')}" for item in recent_summaries]
    ) or "暂无已记录的章节摘要。"

    return f"""
你是章节策划 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划。'}

所属分卷大纲：
{volume_outline or '当前章节未指定分卷，或该分卷尚无大纲。'}

所属剧情段大纲：
{arc_outline or '当前章节未指定剧情段，或该剧情段尚无大纲。'}

所属分卷已批准讨论结论：
{volume_discussion_context or '当前分卷暂无已批准讨论结论。'}

所属剧情段已批准讨论结论：
{arc_discussion_context or '当前剧情段暂无已批准讨论结论。'}

当前章节已批准讨论结论：
{chapter_discussion_context or '当前章节暂无已批准讨论结论。'}

最近章节摘要：
{recent_summary_text}

当前要设计第 {chapter_no} 章。

用户要求：
{user_requirement}

请输出：
1. 本章目标
2. 本章冲突
3. 出场人物
4. 场景安排
5. 情绪节奏
6. 结尾钩子
7. 详细分场景细纲

要求补充：
1. 尽量与全书大纲保持一致
2. 如果存在分卷大纲，优先保持与当前分卷目标、冲突、阶段推进一致
3. 如果存在分卷已批准讨论结论，优先遵守其中明确的本卷目标、结构重心和限制条件
4. 如果存在剧情段大纲或已批准讨论结论，优先保证本章服务于当前剧情段的关键事件与推进目标
5. 如果存在当前章节已批准讨论结论，优先遵守其中明确的本章目标、场景重心和风险提醒
6. 尽量承接最近章节摘要中的剧情状态
7. 如果用户要求与上游规划冲突，明确给出折中处理方式
8. 所有场景按字数分配规划，不要按时间（分钟/秒）划分
9. 每个场景标注预计占用字数
"""


def discuss_chapter_prompt(
    memory: dict,
    outline: str,
    volume_outline: str,
    arc_outline: str,
    volume_discussion_context: str,
    arc_discussion_context: str,
    chapter_discussion_context: str,
    recent_summaries: list[dict],
    chapter_no: int,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    recent_summary_text = "\n".join(
        [f"- 第{item.get('chapter_no', '?')}章：{item.get('summary', '')}" for item in recent_summaries]
    ) or "暂无已记录的章节摘要。"

    return f"""
你是章节讨论 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划。'}

所属分卷大纲：
{volume_outline or '当前章节未指定分卷，或该分卷尚无大纲。'}

所属剧情段大纲：
{arc_outline or '当前章节未指定剧情段，或该剧情段尚无大纲。'}

所属分卷已批准讨论结论：
{volume_discussion_context or '当前分卷暂无已批准讨论结论。'}

所属剧情段已批准讨论结论：
{arc_discussion_context or '当前剧情段暂无已批准讨论结论。'}

当前章节已批准讨论结论：
{chapter_discussion_context or '当前章节暂无已批准讨论结论。'}

最近章节摘要：
{recent_summary_text}

当前要讨论第 {chapter_no} 章。

用户要求：
{user_requirement}

请先不要直接输出最终细纲，而是生成一个章节讨论式规划结果，帮助用户确认本章方向。输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "章节讨论",
  "chapter_goal": "",
  "current_understanding": "",
  "key_constraints": [],
  "options": [
    {{
      "title": "",
      "summary": "",
      "strengths": [],
      "risks": []
    }}
  ],
  "open_questions": [],
  "risks": [],
  "recommended_direction": "",
  "approval_ready": false
}}

要求：
1. 明确本章目标、冲突和叙事功能
2. 如果存在分卷大纲、剧情段大纲或已批准讨论结论，讨论结论必须与这些上游规划节点保持一致或明确说明偏离原因
3. 提出 2-3 个可执行的章节方向或场景组织方案
4. 说明每个方案的节奏、风险和适配条件
5. 列出需要用户确认的关键问题
6. 如果信息足够，请给出推荐方向并标明 approval_ready=true
"""


def arc_outline_prompt(
    memory: dict,
    story_outline: str,
    volume_outline: str,
    arc_no: int,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    approved_discussion_context: str,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是长篇小说剧情段规划 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划剧情段。'}

所属分卷大纲：
{volume_outline or '当前剧情段未指定分卷，或该分卷尚无大纲。'}

当前要规划 Arc {arc_no:03d}。

剧情段标题：
{arc_title or '未命名剧情段'}

剧情段摘要：
{arc_summary or '暂无剧情段摘要。'}

预计章节数：
{estimated_chapter_count or '未设置'}

目标总字数范围：
{target_word_count_range or '未设置'}

已批准讨论结论：
{approved_discussion_context or '当前剧情段暂无已批准讨论结论。'}

用户要求：
{user_requirement or '用户未提供额外要求，请优先补全该剧情段的关键事件链与推进作用。'}

请生成该剧情段大纲，至少包含：
1. 剧情段目标与叙事功能
2. 起点状态与终点状态
3. 关键冲突升级链条
4. 关键事件与转折点
5. 角色推进重点
6. 章节分配建议
7. 节奏与高潮设计
8. 与上游分卷目标的对应关系

要求补充：
1. 必须与全书大纲和所属分卷大纲保持一致
2. 结果应适合作为后续章节讨论和章节细纲生成的直接上游依据
3. 如果存在估算章节数或目标字数范围，尽量在结构中体现分配思路
4. 如果存在已批准讨论结论，优先遵守其中明确的目标、推进结构与约束条件
5. 如果用户要求与上游规划冲突，明确说明折中方案
"""


def discuss_arc_prompt(
    memory: dict,
    story_outline: str,
    volume_outline: str,
    arc_no: int,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是剧情段规划讨论 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求讨论该剧情段方向。'}

所属分卷大纲：
{volume_outline or '当前剧情段未指定分卷，或该分卷尚无大纲。'}

当前要讨论 Arc {arc_no:03d}。

剧情段标题：
{arc_title or '未命名剧情段'}

剧情段摘要：
{arc_summary or '暂无剧情段摘要。'}

预计章节数：
{estimated_chapter_count or '未设置'}

目标总字数范围：
{target_word_count_range or '未设置'}

用户要求：
{user_requirement or '用户暂未补充剧情段要求，请优先讨论该剧情段的目标与推进结构。'}

请先不要直接输出最终剧情段大纲，而是生成一个讨论式规划结果，帮助用户确认该剧情段方向。输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "剧情段讨论",
  "arc_goal": "",
  "current_understanding": "",
  "key_constraints": [],
  "options": [
    {{
      "title": "",
      "summary": "",
      "strengths": [],
      "risks": []
    }}
  ],
  "open_questions": [],
  "risks": [],
  "recommended_direction": "",
  "approval_ready": false
}}

要求：
1. 明确该剧情段的目标、关键推进任务和阶段性终点
2. 如果存在所属分卷大纲，讨论结论必须与该分卷目标保持一致或明确说明偏离原因
3. 提出 2-3 个可执行的剧情段结构方案
4. 说明每个方案的节奏、风险和适配条件
5. 列出仍需用户确认的关键问题
6. 如果信息足够，请给出推荐方向并标明 approval_ready=true
"""


def discuss_outline_turn_prompt(
    memory: dict,
    user_idea: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是长篇小说大纲讨论助手。

你的目标不是一次性给结论，而是和用户持续讨论，并在每一轮对话后更新当前结论。

规则约束：
{rules_text}

当前小说设定：
{memory}

{format_story_state_guidance(memory)}

用户最初想法：
{user_idea}

历史对话：
{format_discussion_history(messages)}

当前已整理出的讨论结论：
{current_discussion or {}}

用户本轮新消息：
{latest_user_message}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "assistant_message": "",
  "discussion": {{
    "title": "全书大纲讨论",
    "current_understanding": "",
    "core_goals": [],
    "key_constraints": [],
    "options": [
      {{
        "title": "",
        "summary": "",
        "strengths": [],
        "risks": []
      }}
    ],
    "open_questions": [],
    "risks": [],
    "recommended_direction": "",
    "approval_ready": false
  }}
}}

要求：
1. `assistant_message` 必须像正常对话一样自然，长度控制在 1-3 段
2. 如果用户信息不足，优先追问关键问题，而不是强行下结论
3. `discussion` 必须基于本轮对话更新，而不是重复原样输出
4. `open_questions` 只保留当前仍待确认的问题
5. 如果已经足够进入正式生成，明确说明原因，并将 `approval_ready` 设为 true
"""


def discuss_volume_turn_prompt(
    memory: dict,
    story_outline: str,
    volume_no: int,
    volume_title: str,
    volume_summary: str,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是分卷方向讨论助手。

你的目标不是一次性给分卷大纲，而是和用户持续讨论第 {volume_no} 卷方向，并在每一轮对话后更新当前结论。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求讨论该分卷方向。'}

当前分卷标题：
{volume_title or '未命名分卷'}

当前分卷摘要：
{volume_summary or '暂无分卷摘要。'}

分卷原始要求：
{user_requirement or '暂无额外要求。'}

历史对话：
{format_discussion_history(messages)}

当前已整理出的讨论结论：
{current_discussion or {}}

用户本轮新消息：
{latest_user_message}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "assistant_message": "",
  "discussion": {{
    "title": "分卷讨论",
    "volume_goal": "",
    "current_understanding": "",
    "key_constraints": [],
    "options": [
      {{
        "title": "",
        "summary": "",
        "strengths": [],
        "risks": []
      }}
    ],
    "open_questions": [],
    "risks": [],
    "recommended_direction": "",
    "approval_ready": false
  }}
}}

要求：
1. `assistant_message` 必须是自然对话式回复，而不是报告体
2. 如果信息不足，优先追问会影响分卷定位和结构的关键问题
3. `discussion` 必须随着本轮对话更新，而不是重复原样输出
4. `open_questions` 只保留当前仍待确认的问题
5. 如果已经足够进入正式生成，明确说明原因，并将 `approval_ready` 设为 true
"""


def discuss_creative_profile_turn_prompt(
    memory: dict,
    current_profile: dict,
    user_idea: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
    retrieval_context: str = "",
) -> str:
    base = f"""
你是创作配置讨论助手。

你的目标不是一次性给最终配置，而是和用户持续讨论项目创作方式，并在每一轮对话后更新当前结论。

规则约束：
{rules_text}

当前小说设定：
{memory}

{format_story_state_guidance(memory)}

当前创作配置：
{current_profile}

用户最初想法：
{user_idea}

历史对话：
{format_discussion_history(messages)}

当前已整理出的讨论结论：
{current_discussion or {}}

用户本轮新消息：
{latest_user_message}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "assistant_message": "",
  "discussion": {{
    "title": "创作配置讨论",
    "current_understanding": "",
    "key_constraints": [],
    "options": [
      {{
        "title": "",
        "summary": "",
        "strengths": [],
        "risks": []
      }}
    ],
    "open_questions": [],
    "risks": [],
    "recommended_direction": "",
    "recommended_profile": {{
      "story_mode": "",
      "target_length": "",
      "target_word_count": "",
      "workflow_depth": "",
      "reference_strength": "",
      "reference_focus": [],
      "allow_canon_deviation": true,
      "conflict_policy": "",
      "notes": ""
    }},
    "approval_ready": false
  }}
}}

要求：
1. `assistant_message` 必须像正常对话一样自然，长度控制在 1-3 段
2. 如果用户信息不足，优先追问会影响配置判断的关键问题
3. `discussion` 必须随着本轮对话更新，而不是重复原样输出
4. `recommended_profile` 必须与本轮讨论结论保持一致，尽量给出完整可执行配置
5. `open_questions` 只保留当前仍待确认的问题
6. 如果已经足够保存为项目创作配置，明确说明原因，并将 `approval_ready` 设为 true
7. 请参考下方补充检索上下文中已上传的资料、知识库内容，来评估合适的参考强度、参考焦点和冲突策略
"""
    return merge_retrieval_context(base, retrieval_context)


def discuss_chapter_turn_prompt(
    memory: dict,
    outline: str,
    volume_outline: str,
    arc_outline: str,
    volume_discussion_context: str,
    arc_discussion_context: str,
    chapter_discussion_context: str,
    recent_summaries: list[dict],
    chapter_no: int,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    recent_summary_text = "\n".join(
        [f"- 第{item.get('chapter_no', '?')}章：{item.get('summary', '')}" for item in recent_summaries]
    ) or "暂无已记录的章节摘要。"

    return f"""
你是章节方向讨论助手。

你的目标不是一次性给细纲，而是和用户持续讨论本章方向，并在每一轮对话后更新当前结论。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划。'}

所属分卷大纲：
{volume_outline or '当前章节未指定分卷，或该分卷尚无大纲。'}

所属剧情段大纲：
{arc_outline or '当前章节未指定剧情段，或该剧情段尚无大纲。'}

所属分卷已批准讨论结论：
{volume_discussion_context or '当前分卷暂无已批准讨论结论。'}

所属剧情段已批准讨论结论：
{arc_discussion_context or '当前剧情段暂无已批准讨论结论。'}

当前章节已批准讨论结论：
{chapter_discussion_context or '当前章节暂无已批准讨论结论。'}

最近章节摘要：
{recent_summary_text}

当前章节：第 {chapter_no} 章

本章原始要求：
{user_requirement}

历史对话：
{format_discussion_history(messages)}

当前已整理出的讨论结论：
{current_discussion or {}}

用户本轮新消息：
{latest_user_message}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "assistant_message": "",
  "discussion": {{
    "title": "章节讨论",
    "chapter_goal": "",
    "current_understanding": "",
    "key_constraints": [],
    "options": [
      {{
        "title": "",
        "summary": "",
        "strengths": [],
        "risks": []
      }}
    ],
    "open_questions": [],
    "risks": [],
    "recommended_direction": "",
    "approval_ready": false
  }}
}}

要求：
1. `assistant_message` 必须是自然对话式回复，而不是报告体
2. 如果当前信息不足，优先追问会影响章节方向的关键问题
3. 如果存在分卷大纲、剧情段大纲或已批准讨论结论，更新后的 `discussion` 必须与这些上游规划节点保持一致或明确说明偏离原因
4. `discussion` 必须随着本轮对话更新
5. `open_questions` 只保留当前还未解决的问题
6. 如果本章方向已经足够明确，给出收束性结论，并将 `approval_ready` 设为 true
"""


def discuss_arc_turn_prompt(
    memory: dict,
    story_outline: str,
    volume_outline: str,
    arc_no: int,
    arc_title: str,
    arc_summary: str,
    estimated_chapter_count: int | None,
    target_word_count_range: str,
    user_requirement: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是剧情段方向讨论助手。

你的目标不是一次性给剧情段大纲，而是和用户持续讨论 Arc {arc_no:03d} 的方向，并在每一轮对话后更新当前结论。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲，请尽量根据当前设定与用户要求讨论该剧情段方向。'}

所属分卷大纲：
{volume_outline or '当前剧情段未指定分卷，或该分卷尚无大纲。'}

剧情段标题：
{arc_title or '未命名剧情段'}

剧情段摘要：
{arc_summary or '暂无剧情段摘要。'}

预计章节数：
{estimated_chapter_count or '未设置'}

目标总字数范围：
{target_word_count_range or '未设置'}

剧情段原始要求：
{user_requirement or '暂无额外要求。'}

历史对话：
{format_discussion_history(messages)}

当前已整理出的讨论结论：
{current_discussion or {}}

用户本轮新消息：
{latest_user_message}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "assistant_message": "",
  "discussion": {{
    "title": "剧情段讨论",
    "arc_goal": "",
    "current_understanding": "",
    "key_constraints": [],
    "options": [
      {{
        "title": "",
        "summary": "",
        "strengths": [],
        "risks": []
      }}
    ],
    "open_questions": [],
    "risks": [],
    "recommended_direction": "",
    "approval_ready": false
  }}
}}

要求：
1. `assistant_message` 必须是自然对话式回复，而不是报告体
2. 如果当前信息不足，优先追问会影响剧情段结构的关键问题
3. 如果存在所属分卷大纲，更新后的 `discussion` 必须与上游分卷目标保持一致或明确说明偏离原因
4. `discussion` 必须随着本轮对话更新
5. `open_questions` 只保留当前还未解决的问题
6. 如果剧情段方向已经足够明确，给出收束性结论，并将 `approval_ready` 设为 true
"""

def write_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    writing_guidance: dict | None = None,
    word_count: str = "2500-3500",
    rules_text: str = "当前无额外规则。"
) -> str:
    writing_guidance = writing_guidance or {}
    focus = writing_guidance.get("focus", []) if isinstance(writing_guidance.get("focus", []), list) else []
    focus_text = "、".join([str(item).strip() for item in focus if str(item).strip()]) or "未特别指定"
    return f"""
你是网文写作 Agent。

规则约束：
{rules_text}

必须遵守以下设定：
{memory}

{format_story_state_guidance(memory)}

章节细纲：
{chapter_outline}

写作指导：
- 文风/基调：{writing_guidance.get('tone', '') or '未特别指定'}
- 节奏：{writing_guidance.get('pacing', '') or '未特别指定'}
- 对话密度：{writing_guidance.get('dialogue_density', '') or '未特别指定'}
- 描写重点：{focus_text}
- 结尾力度：{writing_guidance.get('ending_strength', '') or '未特别指定'}
- 补充要求：{writing_guidance.get('extra_requirements', '') or '无'}

请写出完整章节正文。

要求：
1. 保持人物设定一致
2. 不要跳过关键情节
3. 有网文节奏感
4. 对话自然
5. 结尾留下推进感
6. 字数约{word_count}字
7. 正文为连续自然段落，不要出现"场景一"、"场景二"之类的标记，不要出现小标题
8. 场景切换用空行分隔，不要用显式的场景标题或编号
9. 如果提供了写作指导，优先在不破坏章节细纲核心任务的前提下落实这些写法要求
"""

def update_memory_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是设定维护 Agent。

规则约束：
{rules_text}

已有设定：
{memory}

{format_story_state_guidance(memory)}

新章节：
{chapter}

请提取本章新增或变化的设定，按 JSON 输出，不要附带额外解释：
{{
  "new_characters": [],
  "world_updates": [],
  "timeline_updates": [],
  "foreshadowing_updates": [],
  "chapter_summary": ""
}}

要求：
1. `new_characters` 必须是数组，元素为字符串或对象
2. `world_updates` 必须是数组
3. `timeline_updates` 必须是数组
4. `foreshadowing_updates` 必须是数组
5. `chapter_summary` 必须是字符串
"""


def compact_memory_prompt(memory: dict, chapter_count: int) -> str:
    return f"""
你是设定管理员，负责压缩小说设定库以节省上下文空间。

当前设定库：
{memory}

{format_story_state_guidance(memory)}

已写章节数：{chapter_count}

请执行以下压缩策略：
1. characters：合并同一个角色的多条描述，删除已退场或无后续作用角色的细节
2. world：合并世界观条目，保留"仍活跃"的设定
3. timeline：只保留最近 20 条最重要的时间线条目，较早的合并为摘要
4. foreshadowing：标记已回收的伏笔，删除已回收条目（除非对后续仍有意义）

按原 JSON 结构输出压缩后的设定库，不要改变字段名，不要附带额外解释。
"""


def review_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    chapter: str,
    rules_text: str = "当前无额外规则。"
) -> str:
    return f"""
你是小说审稿 Agent。

规则约束：
{rules_text}

当前设定：
{memory}

{format_story_state_guidance(memory)}

章节细纲：
{chapter_outline}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "status": "pass|revise|blocked",
  "summary": "",
  "strengths": [],
  "issues": [],
  "consistency_checks": {{
    "characters": "",
    "world": "",
    "timeline": "",
    "foreshadowing": ""
  }},
  "pacing": "",
  "next_action": ""
}}

要求：
1. 优先指出角色一致性、世界设定、时间线、伏笔回收方面的问题
2. 如果没有明显问题，也要明确说明通过项
3. `status` 只能是 `pass`、`revise`、`blocked` 之一
4. `strengths` 和 `issues` 必须是字符串数组
"""


def character_analysis_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是角色一致性分析 Agent。

规则约束：
{rules_text}

当前设定：
{memory}

{format_story_state_guidance(memory)}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "角色分析",
  "character_overview": [],
  "consistency_findings": [],
  "relationship_progression": [],
  "issues": [],
  "recommendations": []
}}

要求：
1. 优先核对角色性格、能力、目标、关系是否前后一致
2. 如果没有明显问题，要明确说明通过项
3. 建议必须具体到可修改的写法或情节处理
"""


def timeline_analysis_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是时间线一致性分析 Agent。

规则约束：
{rules_text}

当前设定：
{memory}

{format_story_state_guidance(memory)}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "时间线分析",
  "key_events": [],
  "timeline_alignment": [],
  "contradictions": [],
  "pacing_assessment": [],
  "recommendations": []
}}

要求：
1. 优先识别事件先后、因果衔接、时间跨度是否合理
2. 如果时间信息不足，也要指出缺口
3. 建议要尽量具体
"""


def foreshadowing_analysis_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是伏笔分析 Agent。

规则约束：
{rules_text}

当前设定：
{memory}

{format_story_state_guidance(memory)}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "伏笔分析",
  "new_foreshadowing": [],
  "callbacks_and_payoffs": [],
  "strength_assessment": [],
  "issues": [],
  "recommendations": []
}}

要求：
1. 说明伏笔是否自然、是否过于直白或过弱
2. 指出哪些已有伏笔被延续，哪些被遗忘
3. 没有明显伏笔时要明确说明
"""


def consistency_check_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是长篇小说一致性审校 Agent。

规则约束：
{rules_text}

当前设定：
{memory}

{format_story_state_guidance(memory)}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "一致性总检查",
  "overall_conclusion": "",
  "character_consistency": [],
  "world_consistency": [],
  "timeline_consistency": [],
  "foreshadowing_and_setup": [],
  "priority_fixes": []
}}

要求：
1. 以问题定位为主，但也要说明没有问题的部分
2. 优先修改项按严重程度排序
3. 结论尽量可执行，避免空泛评价
"""


def organize_reference_prompt(
    source_title: str,
    raw_text: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是同人小说资料整理 Agent。

规则约束：
{rules_text}

资料标题：
{source_title}

原始资料：
{raw_text}

请把这份资料拆分整理成适合写作检索的结构化条目，输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "source_title": "",
  "source_summary": "",
  "entries": [
    {{
      "source_type": "external_source|external_character_sheet|external_location_sheet|external_organization_sheet|external_timeline_note|external_canon_event|external_world_rule|external_artifact_note",
      "title": "",
      "summary": "",
      "content": "",
      "tags": [],
      "extra_fields": {{}}
    }}
  ],
  "notes": []
}}

要求：
1. 尽量按角色、地点、组织、时间线事件、世界规则、道具等拆分
2. 如果原文中包含多个设定实体，优先拆成多个条目，不要全部塞进一个大条目
3. `source_type` 必须从给定枚举中选择最合适的类型
4. `summary` 用于短摘要，`content` 用于保留可检索细节
5. `extra_fields` 只保留高价值结构信息，例如阵营、能力、首次登场、所属组织、时间点、关系、来源说明
6. `notes` 可以写你发现的资料缺口、模糊点或冲突点
    """


def extract_reference_knowledge_prompt(
    source_title: str,
    raw_text: str,
    enabled_categories: list[str],
    rules_text: str = "当前无额外规则。",
) -> str:
    categories_text = ", ".join(enabled_categories) if enabled_categories else "全部分类"
    return f"""
你是同人小说资料知识提取总管。

你的任务不是改写资料，而是从资料中提取后续写作可复用的结构化知识。请保守提取，必须能从原文找到依据。

规则约束：
{rules_text}

资料标题：
{source_title}

启用的知识分类：
{categories_text}

可用分类说明：
- characters：角色知识，包含身份、性格、动机、行为习惯、说话风格、角色禁忌
- items：物品与道具，包含武器、装备、特殊物品、来源、使用限制
- abilities：技能与能力，包含能力效果、代价、弱点、成长路线、使用条件
- world_rules：世界观规则，包含制度、文化、规则、阵营、历史背景
- locations：地点资料，包含场景、地理、氛围、重要设施
- organizations：组织资料，包含组织目标、成员、制度、阵营关系
- timeline_events：事件与时间线，包含事件时间、因果、后续影响
- relationships：角色关系，包含亲密、冲突、权力、依赖、关系变化
- writing_style：写作风格，包含叙事视角、节奏、氛围、描写习惯
- dialogue_style：对白风格，包含口癖、语气、句式、称呼习惯
- narrative_techniques：写作手法，包含铺垫、反转、悬念、情绪推进、场景切换
- constraints：硬性约束，包含不能违背的原作规则、设定边界、禁用写法

原始资料：
{raw_text}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "source_title": "",
  "source_summary": "",
  "items": [
    {{
      "category": "characters|items|abilities|world_rules|locations|organizations|timeline_events|relationships|writing_style|dialogue_style|narrative_techniques|constraints",
      "name": "",
      "summary": "",
      "details": {{
        "字段名": "字段内容"
      }},
      "evidence": [
        {{
          "source_title": "",
          "quote": "",
          "note": ""
        }}
      ],
      "confidence": 0.7,
      "tags": []
    }}
  ],
  "notes": []
}}

要求：
1. 只输出启用分类中的内容；如果启用分类为空，则可按全部分类提取
2. 每条知识必须有明确 name 和 summary
3. evidence.quote 尽量摘录短证据，不要大段复制原文
4. confidence 表示你对该条提取的确信程度，范围 0-1
5. 对写作风格、对白风格、写作手法也要尽量提取，但不要把剧情设定误塞进去
6. 遇到资料含混、互相矛盾或需要用户判断的地方，写入 notes
7. 不要发明原文没有的信息
"""


def creative_structure_prompt(
    memory: dict,
    creative_profile: dict,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是同人小说动态创作规划助手。

请根据项目创作配置，为当前需求生成一个适配长度的创作结构。你的目标是给后续正文写作提供足够清晰的计划，但不要强行使用分卷、剧情段等长篇层级。

规则约束：
{rules_text}

项目设定：
{memory}

创作配置：
{creative_profile}

用户需求：
{user_requirement}

请输出 Markdown，不要输出 JSON。结构建议如下：

# 创作结构

## 创作目标

## 参考策略

说明这次应如何使用原作资料、项目设定、参考资料和文风资料。

## 核心设定取舍

说明哪些设定必须保留，哪些可以按需求改写。

## 主要角色与关系

## 剧情结构

根据目标长度选择合适结构：
- 片段：场景目标、冲突点、收束点
- 短篇：开端、推进、转折、高潮、余韵
- 中篇：主要章节或段落安排
- 续写：承接点、状态变化、下一步冲突
- 前传：时间边界、原设约束、因果铺垫
- 穿越/新环境：原角色核心、新环境规则、适配冲突

## 风格与写法要求

## 风险与注意事项

要求：
1. 根据创作配置决定规划粒度，不要机械套用长篇流程
2. 明确资料参考强度如何影响本次生成
3. 如果是轻参考或穿越/新环境，说明哪些原设可以弱化
4. 如果是强参考、严格原作、续写或前传，说明哪些设定不能违背
5. 输出要能直接作为后续正文写作依据
"""


def arc_chapter_plan_prompt(
    memory: dict,
    story_outline: str,
    volume_outline: str,
    arc_outline: str,
    arc_no: int,
    start_chapter_no: int,
    chapter_count: int,
    target_word_count_range: str,
    user_requirement: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是长篇小说剧情段章节分配 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

全书大纲：
{story_outline or '暂无全书大纲。'}

所属分卷大纲：
{volume_outline or '当前剧情段未指定分卷，或该分卷尚无大纲。'}

当前剧情段大纲：
{arc_outline or '当前剧情段尚无大纲，请根据已有信息做保守规划。'}

当前要规划 Arc {arc_no:03d}，从第 {start_chapter_no} 章开始，共 {chapter_count} 章。

目标总字数范围：
{target_word_count_range or '未设置'}

用户补充要求：
{user_requirement or '无'}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "剧情段章节分配",
  "arc_goal": "",
  "planning_assumptions": [],
  "chapters": [
    {{
      "chapter_no": 1,
      "title": "",
      "chapter_goal": "",
      "conflict": "",
      "expected_word_count": "",
      "key_events": [],
      "foreshadowing_dependencies": []
    }}
  ],
  "risks": []
}}

要求：
1. chapters 数量必须尽量等于用户要求的章节数
2. chapter_no 从指定起始章节编号连续递增
3. 每章必须有明确目标、冲突、关键事件和预计字数
4. 如果上游规划不足，请在 planning_assumptions 中说明你的保守假设
5. 不要写正文，只做章节分配计划
"""


def evaluate_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    chapter: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是长篇小说质量评估 Agent。

规则约束：
{rules_text}

小说设定：
{memory}

{format_story_state_guidance(memory)}

章节细纲：
{chapter_outline or '暂无章节细纲。'}

章节正文：
{chapter}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "title": "章节质量评估",
  "overall_score": 0,
  "character_consistency_score": 0,
  "plot_progression_score": 0,
  "information_density_score": 0,
  "emotional_impact_score": 0,
  "foreshadowing_score": 0,
  "prose_quality_score": 0,
  "strengths": [],
  "issues": [],
  "revision_priorities": [],
  "summary": ""
}}

评分要求：
1. 所有分数为 0-100 的整数
2. 优先评估该章节是否服务于长篇连载推进
3. 明确指出最值得先改的 3-5 个问题
4. 如果没有足够上下文，请在 summary 中说明不确定性，但仍给出可用评估
"""
