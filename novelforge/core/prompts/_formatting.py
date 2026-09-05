"""Shared prompt formatting helpers and rule labels."""

RULE_LABELS = {
    "all": "通用规则",
    "outline": "大纲生成规则",
    "chapter_outline": "章节细纲规则",
    "write": "正文写作规则",
    "review": "章节审阅规则",
    "setting_extraction": "设定提炼规则",
}


def format_story_state_guidance(memory: dict) -> str:
    canon_mode = memory.get("canon_mode", "")
    au_rules = memory.get("au_rules", [])
    relationships = memory.get("relationships", [])
    active_constraints = memory.get("active_constraints", [])
    setting_context = str(memory.get("_setting_context", "") or "").strip()
    setting_section = f"""

统一优先设定条目：
{setting_context}
""" if setting_context else ""
    return f"""
故事状态说明：
1. `canon_mode`：{canon_mode or '未设置'}
2. `au_rules`：{au_rules or '无'}
3. `relationships`：{relationships or '无'}
4. `active_constraints`：{active_constraints or '无'}
{setting_section}
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


def format_rules_for_prompt(
    global_rules: dict,
    project_rules: dict,
    scope: str,
    story_rules: dict | None = None,
    conflict_resolutions: list[dict] | None = None,
) -> str:
    lines = [
        "规则冲突解决机制：",
        "- 人工冲突裁决优先于普通生成规则。",
        "- 如果没有人工裁决，默认优先级为：故事规则 > 项目规则 > 全局规则。",
        "- 同一层级内，当前能力的专用规则优先于通用规则。",
        "- 如果仍无法判断，遵循更具体、更贴近当前故事上下文的要求，并在输出中保持一致。",
    ]
    _intro_line_count = len(lines)

    cleaned_resolutions = [
        item for item in (conflict_resolutions or [])
        if str(item.get("decision", "") or "").strip()
    ]
    if cleaned_resolutions:
        lines.append("")
        lines.append("人工冲突裁决：")
        for item in cleaned_resolutions:
            source = str(item.get("source", "") or "").strip()
            title = str(item.get("title", "") or "").strip()
            decision = str(item.get("decision", "") or "").strip()
            prefix = f"{source}裁决" if source else "裁决"
            if title:
                prefix += f" / {title}"
            lines.append(f"- {prefix}：{decision}")

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
        if len(lines) == _intro_line_count or (cleaned_resolutions and lines[-1] != ""):
            lines.append("")
        lines.append(f"{label}：")
        lines.extend([f"- {item}" for item in cleaned])

    return "\n".join(lines)

def merge_retrieval_context(prompt: str, retrieval_context: str) -> str:
    if not retrieval_context.strip() or retrieval_context.strip() == "未检索到额外上下文。":
        return prompt
    return f"""{prompt}

补充检索上下文：
{retrieval_context}
"""
