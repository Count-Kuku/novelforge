"""Chapter review and analysis prompts."""

from novelforge.core.prompts._formatting import format_story_state_guidance

def review_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    chapter: str,
    rules_text: str = "当前无额外规则。"
) -> str:
    return f"""
你是章节改稿门禁 Agent。

你的任务是判断本章是否可以进入下一步，而不是做完整质量评分或专项一致性分析。
请只抓会影响继续写作、记忆更新或发布前改稿的关键问题。

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
1. `status` 只能是 `pass`、`revise`、`blocked` 之一
2. `issues` 只列最需要优先处理的 1-5 个问题，避免展开成完整分析报告
3. `consistency_checks` 只做门禁级简短判断：通过 / 需复查 / 阻塞，并说明一句原因
4. 不要给分数；量化评分由综合章节评价中的评分部分负责
5. 不要展开角色、时间线、伏笔的细项诊断；专项诊断由综合章节评价中的一致性诊断部分负责
6. 如果没有明显问题，也要明确说明通过项
7. `strengths` 和 `issues` 必须是字符串数组
"""


def character_analysis_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是角色一致性分析 Agent。

只分析角色相关问题：性格、能力、目标、关系、行为动机和前后变化。不要评价整体章节质量或给分。

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

只分析事件顺序、因果链、时间跨度、已知历史和当前章节之间的连续性。不要评价整体章节质量或给分。

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

只分析伏笔、铺垫、回收、遗忘线索和后续承接风险。不要评价整体章节质量或给分。

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

你的任务是做专项连续性诊断，定位角色、世界观、时间线、伏笔和既有设定之间的矛盾或缺口。
不要评价文笔好坏，不要给章节分数，也不要替代审阅页面给出 pass/revise/blocked。

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
1. 以连续性问题定位为主，但也要说明没有问题的部分
2. 优先修改项按严重程度排序
3. 每个问题尽量指出涉及的设定、章节文本表现和建议修法
4. 不要评价整体写作质量或打分
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
