def outline_prompt(memory: dict, user_idea: str) -> str:
    return f"""
你是一个网络小说主编，擅长同人小说、长篇规划、爽点设计。

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

def chapter_outline_prompt(memory: dict, chapter_no: int, user_requirement: str) -> str:
    return f"""
你是章节策划 Agent。

小说设定：
{memory}

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
"""

def write_chapter_prompt(memory: dict, chapter_outline: str) -> str:
    return f"""
你是网文写作 Agent。

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
6. 字数约2500-3500字
"""

def update_memory_prompt(memory: dict, chapter: str) -> str:
    return f"""
你是设定维护 Agent。

已有设定：
{memory}

新章节：
{chapter}

请提取本章新增或变化的设定，按 JSON 输出：
{{
  "new_characters": [],
  "world_updates": [],
  "timeline_updates": [],
  "foreshadowing_updates": [],
  "chapter_summary": ""
}}
"""