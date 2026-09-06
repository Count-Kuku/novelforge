"""Chapter writing and free-form creative prompts."""

from novelforge.core.prompts._formatting import format_story_state_guidance

def write_chapter_prompt(
    memory: dict,
    chapter_outline: str,
    writing_guidance: dict | None = None,
    word_count: str = "2500-3500",
    rules_text: str = "当前无额外规则。",
    assembled_context: str | None = None,
) -> str:
    writing_guidance = writing_guidance or {}
    focus = writing_guidance.get("focus", []) if isinstance(writing_guidance.get("focus", []), list) else []
    focus_text = "、".join([str(item).strip() for item in focus if str(item).strip()]) or "未特别指定"
    if assembled_context is not None:
        context_section = f"""
本次已装配上下文：
{assembled_context or '当前没有额外上下文。'}
"""
        guidance_section = ""
    else:
        context_section = f"""
规则约束：
{rules_text}

必须遵守以下设定：
{memory}

{format_story_state_guidance(memory)}
"""
        guidance_section = f"""
写作指导：
- 文风/基调：{writing_guidance.get('tone', '') or '未特别指定'}
- 节奏：{writing_guidance.get('pacing', '') or '未特别指定'}
- 对话密度：{writing_guidance.get('dialogue_density', '') or '未特别指定'}
- 描写重点：{focus_text}
- 结尾力度：{writing_guidance.get('ending_strength', '') or '未特别指定'}
- 补充要求：{writing_guidance.get('extra_requirements', '') or '无'}
"""
    return f"""
你是章节写作 Agent。

{context_section}

章节细纲：
{chapter_outline}

{guidance_section}

请写出完整章节正文。

要求：
1. 保持人物设定一致
2. 不要跳过关键情节
3. 字数约{word_count}字
4. 如果提供了写作指导，优先在不破坏章节细纲核心任务的前提下落实这些写法要求
"""


def creative_fragment_prompt(
    assembled_context: str,
    session_goal: str,
    user_message: str,
    action_type: str,
    word_count: str,
    web_evidence: str = "",
) -> str:
    action_instruction = {
        "generate": "这是会话的首个片段，请建立清晰可继续的场景。",
        "continue": "承接最近已接受片段继续写，不要复述已经发生的内容。",
        "rewrite": "从相同父节点重新创作当前片段，不要参考被替代版本的具体措辞。",
        "branch": "从指定父片段建立新的剧情分支，允许采用不同走向。",
        "revise": "根据用户要求修订当前方向，同时保持已接受事实不变。",
    }.get(action_type, "根据用户本轮要求生成可继续创作的正文片段。")
    return f"""
你是自由创作写作 Agent。你的任务是和用户逐段完成小说正文。

本次已装配上下文：
{assembled_context or "当前没有额外上下文。"}

{f"本轮联网检索资料（仅作外部参考；与故事内已接受事实冲突时以正文为准，不要盲目照搬）：\n{web_evidence}" if web_evidence else ""}会话目标：
{session_goal or "未单独指定，以本轮要求为准。"}

本轮用户要求：
{user_message}

本轮操作：
{action_type}

操作要求：
{action_instruction}

请直接输出小说正文片段，不要输出标题、分析、计划、JSON、解释或 Markdown 代码块。

要求：
1. 目标长度约 {word_count or "800-1200"} 字
2. 严格遵守角色卡、世界观、关系、时间线和硬性约束
3. 已接受片段属于当前会话事实，不得无故推翻
4. 对检索资料中没有明确支持的内容保持克制
5. 本轮只完成适合一个片段的推进，保留自然的继续空间
"""


def creative_session_summary_prompt(
    previous_summary: str,
    accepted_fragments: str,
) -> str:
    return f"""
你是小说创作会话记忆整理 Agent。

请把已经接受的正文压缩成后续续写可直接使用的状态摘要。不要评价文笔，不要添加原文没有的事实。

已有滚动摘要：
{previous_summary or "暂无。"}

新增已接受片段：
{accepted_fragments}

请使用以下固定结构输出纯文本，不要使用 JSON：
- 已发生事件：
- 当前时间与地点：
- 在场及相关人物：
- 人物状态与已知信息：
- 关系变化：
- 尚未完成的冲突：
- 伏笔与后续承接：
- 当前叙事视角与语气：

每项只保留后续续写真正需要的信息，总长度控制在 1200 字以内。
"""


def compile_creative_fragments_prompt(
    fragments: str,
    target_word_count: str = "",
) -> str:
    return f"""
你是小说正文衔接编辑。请把下列已经由用户接受的片段整理成一篇连续正文。

已接受片段：
{fragments}

要求：
1. 不改变事件结果、角色关系、世界规则和关键对白含义
2. 只处理重复开头、转场、指代和时态等衔接问题
3. 不新增重要剧情，不删除关键事实
4. 直接输出整理后的正文，不要说明修改过程
5. 目标长度：{target_word_count or "保持与原片段总长度接近"}
"""


def setting_extraction_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return f"""
你是章节设定提炼 Agent。

规则约束：
{rules_text}

已有正式设定：
{memory}

{format_story_state_guidance(memory)}

新章节：
{chapter}

请提取本章新增或变化、值得进入待确认知识队列的稳定设定，按 JSON 输出，不要附带额外解释：
{{
  "new_characters": [],
  "world_updates": [],
  "timeline_updates": [],
  "foreshadowing_updates": [],
  "chapter_summary": ""
}}

要求：
1. `new_characters` 必须是数组，元素为字符串或对象；对象可带 `name`（角色名）与下列槽位字段：
   `location`（当前位置）、`status`（当前状态）、`holding`（持有物）、`appearance`（外貌）、
   `personality`（性格）、`abilities`（能力）、`affiliations`（所属组织）。
   只有明确发生变化或首次出现的槽位才写，不要重复已有设定。
2. `world_updates` 必须是数组，元素为字符串或对象；对象可带 `name`（规则/地点/势力名）与
   `status`（地点/势力的当前状态，如"被围困""覆灭""结盟"）。
3. `timeline_updates` 必须是数组
4. `foreshadowing_updates` 必须是数组
5. `chapter_summary` 必须是字符串
"""


def update_memory_prompt(memory: dict, chapter: str, rules_text: str = "当前无额外规则。") -> str:
    return setting_extraction_prompt(memory, chapter, rules_text)


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
