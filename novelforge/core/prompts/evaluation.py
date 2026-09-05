"""Structure, evaluation, and entity-context prompts."""

from novelforge.core.prompts._formatting import format_story_state_guidance

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

## 优先设定取舍

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

你的任务是量化评估本章质量，适合比较不同章节或同一章节的不同版本。
不要做完整改稿门禁，也不要展开专项一致性诊断；只保留影响评分的关键原因。

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
2. 评分应覆盖剧情推进、信息密度、情绪效果、伏笔使用、文字完成度等维度
3. `issues` 和 `revision_priorities` 只列影响分数的关键原因，避免展开成完整审阅报告
4. 如发现严重一致性问题，可体现在对应分数和一句扣分原因中，详细诊断交给综合章节评价中的一致性诊断部分
5. 如果没有足够上下文，请在 summary 中说明不确定性，但仍给出可用评估
"""


def comprehensive_chapter_evaluation_prompt(
    memory: dict,
    chapter_outline: str,
    chapter: str,
    rules_text: str = "当前无额外规则。",
) -> str:
    return f"""
你是章节综合评价 Agent。

你的任务是把“审阅门禁、质量评分、一致性诊断”合成一份章节体检报告。
请一次性判断本章是否能进入下一步、给出量化评分，并定位最重要的连续性问题。

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
  "title": "章节综合评价",
  "status": "pass|revise|blocked",
  "verdict_summary": "",
  "overall_score": 0,
  "character_consistency_score": 0,
  "plot_progression_score": 0,
  "information_density_score": 0,
  "emotional_impact_score": 0,
  "foreshadowing_score": 0,
  "prose_quality_score": 0,
  "strengths": [],
  "blocking_issues": [],
  "issues": [],
  "consistency_diagnosis": {{
    "characters": [],
    "world": [],
    "timeline": [],
    "foreshadowing": []
  }},
  "revision_priorities": [],
  "next_action": "",
  "summary": ""
}}

要求：
1. `status` 只能是 `pass`、`revise`、`blocked` 之一。
2. `pass` 表示可进入后续章节或记忆更新；`revise` 表示建议先改但不阻塞理解；`blocked` 表示存在会破坏后续写作的重大问题。
3. 所有分数为 0-100 的整数，分数要和问题严重度一致。
4. `blocking_issues` 只放真正阻塞后续写作的问题；普通问题放入 `issues`。
5. `consistency_diagnosis` 只写角色、世界观、时间线、伏笔相关诊断。
6. `revision_priorities` 按修改优先级排序，最多 6 条。
7. 不要把报告写得过长，重点是能指导下一步改稿。
"""


def plan_entity_context_query_prompt(
    capability: str,
    query_text: str,
    known_entities_text: str = "",
    rules_text: str = "当前无额外规则。",
) -> str:
    """P1：实体识别 + 查询规划 prompt（refactor 2 · D1）。

    输入本次生成/规划场景的文本（正文时是大纲/细纲，规划时是创作想法/上一级大纲），
    让模型输出「本次上下文真正需要的实体清单」，供生成侧按实体取事实并分路由召回。
    只识别「本次写作会用到的事实承载者」，不要求枚举整库设定。
    """
    return f"""你是生成上下文实体识别 Agent。

你的任务：判断「这一次生成/规划」，上下文里真正需要哪些**已确认实体**的事实，输出实体清单。
识别准则是「本次写作会用到的设定承载者」——不是资料库里所有角色，而是本次文本明确涉及或
明显隐含、写下去必须知道其设定/状态的那批实体。

规则约束：
{rules_text}

本次生成场景类型：{capability}

待分析文本（细纲/大纲/创作想法/写作要求）：
{query_text}

{"知识库中已确认的核心实体（供名称对齐，不要照单全收）：\n" + known_entities_text if known_entities_text else ""}

请输出 JSON，不要附带额外解释或 Markdown。格式：
{{
  "entities": [
    {{
      "name": "实体的规范名（与知识库一致的规范名；别名请归一到规范名）",
      "type": "character|organization|location|item|ability|event|rule",
      "mention": "direct|alias|implicit",
      "purpose": "一句话说明为什么本次需要它"
    }}
  ]
}}

要求：
1. `entities` 是数组；不确定是否与知识库对应时，仍给出名称，由系统做别名解析。
2. `mention` 说明它在文本里以什么形式出现：direct=直接点名，alias=用了别名/称呼，implicit=没点名但情节隐含需要。
3. 只输出真正必要的实体，宁缺毋滥——每多一个实体都会挤占上下文预算。
4. 若文本没有足够的实体线索（如全新创作、无任何设定依赖），输出空数组即可，不要臆造。
"""
