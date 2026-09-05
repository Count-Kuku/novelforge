"""Outline/volume/arc/chapter planning and discussion prompts."""

from novelforge.core.prompts._formatting import (
    format_story_state_guidance,
    merge_retrieval_context,
)

def outline_prompt(memory: dict, user_idea: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是长篇小说规划 Agent。

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


def discuss_outline_prompt(memory: dict, user_idea: str, rules_text: str = "当前无额外规则。", retrieval_context: str = "") -> str:
    base = f"""
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
6. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)


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
    "worldline_id": "main",
    "worldline_label": "本项目主线",
    "worldline_retrieval_mode": "prefer"
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
7. 请参考下方补充检索上下文中已上传的资料、知识库内容，来评估合适的参考强度、参考焦点、冲突策略和世界线设置
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

已保存讨论结论：
{approved_discussion_context or '当前分卷暂无已保存讨论结论。'}

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
4. 如果存在已保存讨论结论，优先遵守其中明确的本卷目标、结构重心与约束条件
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
    retrieval_context: str = "",
) -> str:
    base = f"""
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
6. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)

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

所属分卷已保存讨论结论：
{volume_discussion_context or '当前分卷暂无已保存讨论结论。'}

所属剧情段已保存讨论结论：
{arc_discussion_context or '当前剧情段暂无已保存讨论结论。'}

当前章节已保存讨论结论：
{chapter_discussion_context or '当前章节暂无已保存讨论结论。'}

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
3. 如果存在分卷已保存讨论结论，优先遵守其中明确的本卷目标、结构重心和限制条件
4. 如果存在剧情段大纲或已保存讨论结论，优先保证本章服务于当前剧情段的关键事件与推进目标
5. 如果存在当前章节已保存讨论结论，优先遵守其中明确的本章目标、场景重心和风险提醒
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
    retrieval_context: str = "",
) -> str:
    recent_summary_text = "\n".join(
        [f"- 第{item.get('chapter_no', '?')}章：{item.get('summary', '')}" for item in recent_summaries]
    ) or "暂无已记录的章节摘要。"

    base = f"""
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

所属分卷已保存讨论结论：
{volume_discussion_context or '当前分卷暂无已保存讨论结论。'}

所属剧情段已保存讨论结论：
{arc_discussion_context or '当前剧情段暂无已保存讨论结论。'}

当前章节已保存讨论结论：
{chapter_discussion_context or '当前章节暂无已保存讨论结论。'}

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
2. 如果存在分卷大纲、剧情段大纲或已保存讨论结论，讨论结论必须与这些上游规划节点保持一致或明确说明偏离原因
3. 提出 2-3 个可执行的章节方向或场景组织方案
4. 说明每个方案的节奏、风险和适配条件
5. 列出需要用户确认的关键问题
6. 如果信息足够，请给出推荐方向并标明 approval_ready=true
7. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)


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

已保存讨论结论：
{approved_discussion_context or '当前剧情段暂无已保存讨论结论。'}

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
4. 如果存在已保存讨论结论，优先遵守其中明确的目标、推进结构与约束条件
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
    retrieval_context: str = "",
) -> str:
    base = f"""
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
7. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)
