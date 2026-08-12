"""Pure deterministic routing for the free-writing conversational protocol."""

from __future__ import annotations

import re


ACTION_TYPES = {
    "write", "revise", "import_sources", "extract_knowledge",
    "query_knowledge", "update_knowledge", "update_config",
    "save_chapter", "clarify",
}
CONFIRMATION_ACTIONS = {
    "extract_knowledge", "update_knowledge", "update_config", "save_chapter",
}

_CONFIG_ALIASES = {
    "文风": ("session", "tone"),
    "语气": ("session", "tone"),
    "节奏": ("session", "pacing"),
    "对话密度": ("session", "dialogue_density"),
    "持续要求": ("session", "extra_requirements"),
    "目标章节": ("session", "target_chapter_no"),
    "参考强度": ("story", "reference_strength"),
    "冲突策略": ("story", "conflict_policy"),
    "目标字数": ("story", "target_word_count"),
    "创作备注": ("story", "notes"),
}


def _after_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text.startswith(prefix):
            return text[len(prefix):].lstrip(" ：:")
    return ""


def _parse_config_patch(text: str) -> tuple[str, dict]:
    body = _after_prefix(text, ("/调整配置", "/配置", "调整配置", "修改配置")) or text
    scopes: set[str] = set()
    patch: dict = {}
    for label, (field_scope, field) in _CONFIG_ALIASES.items():
        match = re.search(
            rf"{re.escape(label)}\s*(?:改成|设为|设置为|=|：|:)\s*([^，,；;\n]+)",
            body,
        )
        if not match:
            continue
        value: object = match.group(1).strip()
        if field == "target_chapter_no":
            number = re.search(r"\d+", str(value))
            if not number:
                continue
            value = int(number.group())
        scopes.add(field_scope)
        patch[field] = value
    return (next(iter(scopes)) if len(scopes) == 1 else "mixed" if scopes else "session"), patch


def _parse_knowledge_update(text: str) -> tuple[dict, dict]:
    body = _after_prefix(text, ("/修改知识", "/更新知识", "修改知识", "更新知识"))
    match = re.match(r"([a-z_]+)\s*[:：/]\s*([\w\-]+)\s+(.+)", body)
    if not match:
        return {}, {}
    category, item_id, changes = match.groups()
    patch: dict = {}
    aliases = {"名称": "name", "摘要": "summary", "状态": "status", "注释": "notes"}
    for part in re.split(r"[，,；;]", changes):
        field_match = re.match(r"([^=：:]+)\s*(?:=|：|:)\s*(.+)", part.strip())
        if not field_match:
            continue
        field, value = field_match.groups()
        normalized = aliases.get(field.strip(), field.strip())
        if normalized in {"name", "summary", "status", "notes"}:
            patch[normalized] = value.strip()
    return {"category": category, "item_id": item_id}, patch


def route_creative_action(text: str, *, has_fragment: bool = False) -> dict:
    clean = " ".join(str(text or "").strip().split())
    if not clean:
        return {"action_type": "clarify", "plan": {"message": "请输入创作要求或命令。"}}

    if clean.startswith(("/导入资料", "/附件", "导入资料", "添加资料")):
        return {
            "action_type": "import_sources", "scope": "session",
            "plan": {"message": "请使用输入框下方的“资料与附件”托盘选择来源和作用域。"},
        }
    if clean.startswith(("/提炼设定", "/提取知识", "提炼设定", "提取知识", "整理这段设定")):
        return {"action_type": "extract_knowledge", "scope": "story", "target": {"active_fragment": True}}
    if clean.startswith(("/查资料", "/查询知识", "/查设定", "查资料", "查询知识", "查一下设定")):
        query = _after_prefix(clean, ("/查资料", "/查询知识", "/查设定", "查资料", "查询知识", "查一下设定"))
        return {
            "action_type": "query_knowledge", "scope": "story",
            "target": {"query": query or clean},
        }
    if clean.startswith(("/修改知识", "/更新知识", "修改知识", "更新知识")):
        target, patch = _parse_knowledge_update(clean)
        if not target or not patch:
            return {
                "action_type": "clarify",
                "plan": {"message": "请使用：/修改知识 分类:知识ID 摘要=新内容"},
            }
        return {"action_type": "update_knowledge", "scope": "story", "target": target, "patch": patch}
    if clean.startswith(("/调整配置", "/配置", "调整配置", "修改配置")) or any(
        re.search(rf"{re.escape(label)}\s*(?:改成|设为|设置为)", clean)
        for label in _CONFIG_ALIASES
    ):
        scope, config_patch = _parse_config_patch(clean)
        if not config_patch or scope == "mixed":
            return {
                "action_type": "clarify",
                "plan": {"message": (
                    "一次动作请只修改会话写作设置或故事配置中的一种；"
                    "例如：/配置 文风=克制，节奏=快推"
                    if scope == "mixed"
                    else "请说明配置差异，例如：/配置 文风=克制，节奏=快推"
                )},
            }
        return {"action_type": "update_config", "scope": scope, "patch": config_patch}
    if clean.startswith(("/保存章节", "/整理成章节", "保存为第", "整理成章节")):
        number = re.search(r"第?\s*(\d+)\s*章?", clean)
        return {
            "action_type": "save_chapter", "scope": "story",
            "target": {"chapter_no": int(number.group(1)) if number else None},
        }
    if clean.startswith(("/重写", "/修改这段")):
        instruction = _after_prefix(clean, ("/重写", "/修改这段"))
        return {
            "action_type": "revise" if has_fragment else "clarify",
            "target": {"instruction": instruction or clean},
            "plan": {} if has_fragment else {"message": "当前还没有可重写的正文片段。"},
        }
    if clean.startswith("/"):
        return {
            "action_type": "clarify",
            "plan": {"message": "未识别该命令。可使用 /查资料、/提炼设定、/配置、/修改知识、/保存章节。"},
        }
    return {"action_type": "write", "scope": "turn", "target": {"instruction": clean}}


def action_requires_confirmation(action_type: str) -> bool:
    return str(action_type or "") in CONFIRMATION_ACTIONS
