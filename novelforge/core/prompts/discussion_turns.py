"""Multi-turn discussion continuation prompts."""

from novelforge.core.prompts._formatting import (
    format_story_state_guidance,
    format_discussion_history,
    merge_retrieval_context,
)

def discuss_outline_turn_prompt(
    memory: dict,
    user_idea: str,
    messages: list[dict],
    current_discussion: dict | None,
    latest_user_message: str,
    rules_text: str = "当前无额外规则。",
    retrieval_context: str = "",
) -> str:
    base = f"""
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
6. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)


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
    retrieval_context: str = "",
) -> str:
    base = f"""
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
6. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)


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
      "worldline_id": "main",
      "worldline_label": "本项目主线",
      "worldline_retrieval_mode": "prefer"
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
7. 请参考下方补充检索上下文中已上传的资料、知识库内容，来评估合适的参考强度、参考焦点、冲突策略和世界线设置
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
    retrieval_context: str = "",
) -> str:
    recent_summary_text = "\n".join(
        [f"- 第{item.get('chapter_no', '?')}章：{item.get('summary', '')}" for item in recent_summaries]
    ) or "暂无已记录的章节摘要。"

    base = f"""
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

所属分卷已保存讨论结论：
{volume_discussion_context or '当前分卷暂无已保存讨论结论。'}

所属剧情段已保存讨论结论：
{arc_discussion_context or '当前剧情段暂无已保存讨论结论。'}

当前章节已保存讨论结论：
{chapter_discussion_context or '当前章节暂无已保存讨论结论。'}

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
3. 如果存在分卷大纲、剧情段大纲或已保存讨论结论，更新后的 `discussion` 必须与这些上游规划节点保持一致或明确说明偏离原因
4. `discussion` 必须随着本轮对话更新
5. `open_questions` 只保留当前还未解决的问题
6. 如果本章方向已经足够明确，给出收束性结论，并将 `approval_ready` 设为 true
7. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)


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
    retrieval_context: str = "",
) -> str:
    base = f"""
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
7. 请参考下方补充检索上下文中的设定、结构化知识和导入资料；如果资料之间存在冲突，请在 `risks` 或 `open_questions` 中提示用户确认
"""
    return merge_retrieval_context(base, retrieval_context)
