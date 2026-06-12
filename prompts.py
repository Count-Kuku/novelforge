RULE_LABELS = {
    "all": "通用规则",
    "outline": "大纲生成规则",
    "chapter_outline": "章节细纲规则",
    "write": "正文写作规则",
    "review": "章节审阅规则",
    "memory_update": "设定更新规则",
}


def format_rules_for_prompt(global_rules: dict, project_rules: dict, scope: str) -> str:
    lines = []

    for label, rules in [
        ("全局通用规则", global_rules.get("all", [])),
        ("项目通用规则", project_rules.get("all", [])),
        (f"全局{RULE_LABELS.get(scope, scope)}", global_rules.get(scope, [])),
        (f"项目{RULE_LABELS.get(scope, scope)}", project_rules.get(scope, [])),
    ]:
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

全书大纲：
{outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划。'}

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
2. 尽量承接最近章节摘要中的剧情状态
3. 如果用户要求与大纲冲突，明确给出折中处理方式
4. 所有场景按字数分配规划，不要按时间（分钟/秒）划分
5. 每个场景标注预计占用字数
"""


def discuss_chapter_prompt(
    memory: dict,
    outline: str,
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

全书大纲：
{outline or '暂无全书大纲，请尽量根据当前设定与用户要求规划。'}

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
2. 提出 2-3 个可执行的章节方向或场景组织方案
3. 说明每个方案的节奏、风险和适配条件
4. 列出需要用户确认的关键问题
5. 如果信息足够，请给出推荐方向并标明 approval_ready=true
"""

def write_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    word_count: str = "2500-3500",
    rules_text: str = "当前无额外规则。"
) -> str:
    return f"""
你是网文写作 Agent。

规则约束：
{rules_text}

必须遵守以下设定：
{memory}

章节细纲：
{chapter_outline}

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
"""

def update_memory_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是设定维护 Agent。

规则约束：
{rules_text}

已有设定：
{memory}

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
