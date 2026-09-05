"""Reference knowledge extraction prompts."""

EXTRACTION_MODE_INSTRUCTIONS = {
    "general": """
通用提取：平衡抽取角色、设定、事件、关系、物品能力、地点组织、文风和硬性约束。适合资料类型不明确的片段。
""",
    "deep": """
深度提取：尽可能覆盖片段中的高价值知识，但要合并同类信息，避免把普通叙述拆成大量低价值条目。
优先输出对后续同人写作有长期复用价值的知识。
""",
    "characters": """
角色专用提取：重点抽取角色身份、性格核心、行为习惯、动机、底线、口癖、称呼、与他人的稳定互动模式。
只有当物品、能力、事件直接服务于角色理解时才输出非角色分类。
""",
    "relationships": """
关系专用提取：重点抽取角色之间的亲密、冲突、权力、依赖、误解、保护、利用、师徒、阵营等关系。
每条关系应尽量写清关系双方、关系类型、情绪基调、变化阶段和可写作张力。
""",
    "timeline": """
时间线专用提取：重点抽取事件、因果、时间顺序、前置条件、后续影响、角色状态变化。
不要把普通背景描述误判成事件；事件名称要可排序、可复查。
""",
    "world": """
设定专用提取：重点抽取世界观规则、组织制度、地点、阵营、能力体系、物品限制和不能违背的原作规则。
优先输出稳定设定和规则边界，少输出临时场景描写。
""",
    "style": """
文风专用提取：重点抽取叙事视角、句式节奏、氛围、描写偏好、对白风格、口癖、场景推进方式。
不要把剧情事实塞进文风分类；如果片段不足以判断文风，请降低 confidence 和 evidence_strength。
""",
    "strict_canon": """
严格原作提取：只抽取原文明确支持、后续同人不能轻易违背的事实、关系、事件和硬性约束。
推测内容必须标为 inferred 或 ambiguous，不能当成 canon。
""",
    "fanfic_reference": """
同人参考提取：抽取对改写有帮助的角色感觉、关系张力、文风氛围、可复用桥段和可保留/可改写的设定边界。
允许保留 inferred 条目，但必须说明证据和不确定性。
""",
}


def extract_reference_knowledge_prompt(
    source_title: str,
    raw_text: str,
    enabled_categories: list[str],
    rules_text: str = "当前无额外规则。",
    extraction_mode: str = "general",
    alias_context: str = "",
    custom_instructions: str = "",
    field_specs_text: str = "",
) -> str:
    categories_text = ", ".join(enabled_categories) if enabled_categories else "全部分类"
    mode_key = extraction_mode if extraction_mode in EXTRACTION_MODE_INSTRUCTIONS else "general"
    mode_instruction = EXTRACTION_MODE_INSTRUCTIONS[mode_key].strip()
    return f"""
你是同人小说资料知识提取总管。

你的任务不是改写资料，而是从资料中提取后续写作可复用的结构化知识。请保守提取，必须能从原文找到依据。

规则约束：
{rules_text}

资料标题：
{source_title}

启用的知识分类：
{categories_text}

已知实体别名：
{alias_context.strip() or "当前无已知别名。"}

用户补充提取要求：
{custom_instructions.strip() or "当前无补充要求。"}

提取模式：
{mode_key}

模式要求：
{mode_instruction}

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

各分类字段规格（带 * 为必填，请尽量按字段填写，不要只堆进 details 自由字典）：
{field_specs_text}

原始资料：
{raw_text}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "source_title": "",
  "source_summary": "",
  "items": [
    {{
      "category": "characters|items|abilities|world_rules|locations|organizations|timeline_events|relationships|writing_style|dialogue_style|narrative_techniques",
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
      "importance": 0.5,
      "evidence_strength": 0.5,
      "canon_status": "canon|inferred|ambiguous|fanon|user_override|unknown",
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
5. importance 表示该条对后续同人写作的长期复用价值，范围 0-1
6. evidence_strength 表示证据强度：原文明确陈述接近 1，弱推断接近 0.3
7. canon_status 必须区分 canon / inferred / ambiguous / fanon / user_override / unknown
8. 对写作风格、对白风格、写作手法也要尽量提取，但不要把剧情设定误塞进去
9. 遇到资料含混、互相矛盾或需要用户判断的地方，写入 notes
10. 如果原文出现已知实体别名，请优先使用主名称作为 name，并在 details 或 tags 中保留别名线索
11. 不要发明原文没有的信息
"""


def consolidate_extracted_knowledge_prompt(
    source_title: str,
    extracted_items_json: str,
    enabled_categories: list[str],
    consolidation_mode: str = "balanced",
    rules_text: str = "当前无额外规则。",
) -> str:
    categories_text = ", ".join(enabled_categories) if enabled_categories else "全部分类"
    mode_text = {
        "balanced": "平衡整理：合并重复实体，保留高价值事实、关系、事件、设定和文风信息。",
        "character_cards": "角色卡优先：优先把同一角色的身份、性格、关系、口吻、能力和禁忌整理成稳定角色卡。",
        "timeline": "时间线优先：优先整理事件顺序、因果、状态变化和后续影响。",
        "strict_canon": "严格原作：只保留证据强、可作为原作约束的条目；弱推断要标为 inferred 或 ambiguous。",
        "style": "文风优先：优先整理叙事视角、节奏、对白、氛围和写作手法，减少剧情事实重复。",
    }.get(consolidation_mode, "平衡整理：合并重复实体，保留高价值资料。")
    return f"""
你是同人小说资料库整理编辑。你的任务是把一批已经从原文片段中抽取出的散乱知识条目，整理成更少、更稳定、更适合后续写作复用的结构化知识。

资料批次：
{source_title}

规则约束：
{rules_text}

启用分类：
{categories_text}

整理模式：
{consolidation_mode}

模式要求：
{mode_text}

待整理条目 JSON：
{extracted_items_json}

请输出 JSON，不要附带额外解释或 Markdown。格式如下：
{{
  "source_title": "",
  "source_summary": "",
  "items": [
    {{
      "category": "characters|items|abilities|world_rules|locations|organizations|timeline_events|relationships|writing_style|dialogue_style|narrative_techniques",
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
      "importance": 0.5,
      "evidence_strength": 0.5,
      "canon_status": "canon|inferred|ambiguous|fanon|user_override|unknown",
      "extraction_mode": "consolidated",
      "source_segment_ids": [],
      "source_segment_titles": [],
      "merged_from_pending_ids": [],
      "tags": []
    }}
  ],
  "notes": []
}}

要求：
1. 合并同一实体、同一关系、同一事件或同一规则的重复条目
2. 不要简单拼接所有 summary，要写成可直接给后续写作使用的稳定资料卡
3. evidence 最多保留最有代表性的短证据；如果原条目只有 note，也可以保留 note
4. merged_from_pending_ids 必须填入被合并条目的 pending_id
5. source_segment_ids/source_segment_titles 尽量合并去重，便于追溯来源
6. 对互相矛盾的信息不要强行合并，拆成多条或写入 notes
7. 只输出启用分类中的内容；如果启用分类为空，则可按全部分类整理
8. 不要发明输入条目中没有的信息
"""


def recall_missed_knowledge_prompt(
    source_title: str,
    raw_text: str,
    extracted_items_json: str,
    enabled_categories: list[str],
    rules_text: str = "当前无额外规则。",
) -> str:
    categories_text = ", ".join(enabled_categories) if enabled_categories else "全部分类"
    return f"""
你是同人小说资料提取的复核员。

下面已经完成了一轮资料提取。请你对照原文，找出**被遗漏**的重要实体、事件、关系、设定或硬性约束，尤其注意：
- 只在原文中短暂出现、但影响后续剧情走向的角色或物品；
- 跨段落前后呼应、单独一段看不出重要性的设定；
- 容易和已有条目混为一谈、但其实应当独立的实体。

资料标题：
{source_title}

启用的知识分类：
{categories_text}

规则约束：
{rules_text}

已提取条目（JSON）：
{extracted_items_json}

原始资料：
{raw_text}

请输出 JSON，格式与已提取条目一致：
{{
  "items": [
    {{
      "category": "characters|items|abilities|world_rules|locations|organizations|timeline_events|relationships|writing_style|dialogue_style|narrative_techniques",
      "name": "",
      "summary": "",
      "details": {{
        "字段名": "字段内容"
      }},
      "evidence": [
        {{
          "quote": "",
          "note": ""
        }}
      ],
      "confidence": 0.7,
      "importance": 0.5,
      "evidence_strength": 0.5
    }}
  ],
  "notes": []
}}

只列出确实被遗漏的条目；如果没有遗漏，items 返回空数组。不要重复已提取条目中的内容。
"""
