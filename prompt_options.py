import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schemas import PromptOption


PROMPT_OPTION_CAPABILITIES = {
    "all": "通用",
    "outline": "全书大纲",
    "chapter_outline": "章节细纲",
    "write": "正文写作",
    "review": "章节审阅",
    "setting_extraction": "设定提炼",
    "extraction": "知识抽取",
    "evaluation": "章节评价",
}

PROMPT_OPTION_CATEGORIES = {
    "planning_method": "规划方法",
    "writing_style": "写作风格",
    "review_rubric": "审稿标准",
    "memory_policy": "设定策略",
    "extraction_focus": "抽取重点",
    "retrieval_policy": "检索策略",
    "character_rule": "角色规则",
    "custom": "自定义",
}

PROMPT_OPTION_SLOTS = {
    "planning_guidance": "规划指导",
    "style_guidance": "文风指导",
    "execution_guidance": "执行要求",
    "review_criteria": "审稿准则",
    "memory_policy": "设定提炼策略",
    "extraction_instruction": "抽取说明",
    "retrieval_preference": "检索偏好",
    "custom": "自定义插槽",
}

BUILTIN_PROMPT_OPTIONS = [
    {
        "id": "builtin_write_fast_webnovel",
        "name": "快节奏网文",
        "capability": "write",
        "category": "writing_style",
        "slot": "style_guidance",
        "priority": 40,
        "enabled": False,
        "content": "正文应保持较高推进密度，减少静态说明；每个场景都要产生情绪、信息或关系变化，并在章节结尾留下可继续阅读的钩子。",
        "tags": ["节奏", "网文"],
    },
    {
        "id": "builtin_write_subtle_emotion",
        "name": "克制细腻心理",
        "capability": "write",
        "category": "writing_style",
        "slot": "style_guidance",
        "priority": 45,
        "enabled": False,
        "content": "优先通过动作、停顿、细节和未说出口的话表现情绪；避免直接解释人物心理，让读者从行为和对话里感到关系变化。",
        "tags": ["心理", "情绪"],
    },
    {
        "id": "builtin_plan_three_beat_hook",
        "name": "三段推进与结尾钩子",
        "capability": "chapter_outline",
        "category": "planning_method",
        "slot": "planning_guidance",
        "priority": 40,
        "enabled": False,
        "content": "章节规划按“开场目标 / 中段转折 / 结尾钩子”组织；每章至少明确一个人物目标、一个阻力、一个新信息或关系变化。",
        "tags": ["章节规划", "钩子"],
    },
    {
        "id": "builtin_outline_character_arc",
        "name": "人物成长优先",
        "capability": "outline",
        "category": "planning_method",
        "slot": "planning_guidance",
        "priority": 45,
        "enabled": False,
        "content": "大纲优先围绕人物缺口、选择代价和关系变化设计主线；事件推进应服务于人物成长，而不是只堆叠设定和冲突。",
        "tags": ["大纲", "人物"],
    },
    {
        "id": "builtin_review_fanfic_consistency",
        "name": "同人一致性严格审稿",
        "capability": "review",
        "category": "review_rubric",
        "slot": "review_criteria",
        "priority": 35,
        "enabled": False,
        "content": "审阅时严格检查人物是否 OOC、设定是否违背已确认原作/项目资料、关系推进是否跳跃；若与高权威资料冲突，应明确指出并建议修订。",
        "tags": ["同人", "一致性"],
    },
    {
        "id": "builtin_memory_long_term_only",
        "name": "只记录长期有效变化",
        "capability": "setting_extraction",
        "category": "memory_policy",
        "slot": "memory_policy",
        "priority": 35,
        "enabled": False,
        "content": "设定提炼只抽取长期有效的事实、关系变化、时间线进展、伏笔和硬约束；不要把临时情绪、一次性措辞或未确认猜测放进候选设定。",
        "tags": ["设定", "长期"],
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\u4e00-\u9fff]+", "_", str(value or "").strip()).strip("_")
    return cleaned[:80] or "prompt_option"


def _fallback_id(raw: dict, prefix: str = "option") -> str:
    seed = "|".join([
        str(raw.get("name", "")),
        str(raw.get("capability", "")),
        str(raw.get("category", "")),
        str(raw.get("content", "")),
    ])
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:10]
    base = _safe_id(str(raw.get("name") or prefix))
    return f"{base}_{digest}"


def _normalize_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in {"true", "1", "yes", "y", "on", "启用"}:
            return True
        if cleaned in {"false", "0", "no", "n", "off", "停用"}:
            return False
    return bool(value)


def normalize_prompt_option(
    raw: dict | PromptOption | None,
    *,
    scope: str = "story",
    built_in: bool = False,
    fallback_id: str = "",
) -> dict:
    item = raw.model_dump() if isinstance(raw, PromptOption) else dict(raw or {})
    timestamp = now_iso()
    option_id = _safe_id(str(item.get("id") or fallback_id or _fallback_id(item)))
    capability = str(item.get("capability") or "write").strip()
    if capability not in PROMPT_OPTION_CAPABILITIES:
        capability = "all"
    category = str(item.get("category") or "custom").strip()
    if category not in PROMPT_OPTION_CATEGORIES:
        category = "custom"
    slot = str(item.get("slot") or "custom").strip()
    if slot not in PROMPT_OPTION_SLOTS:
        slot = "custom"

    try:
        priority = int(item.get("priority", 50))
    except (TypeError, ValueError):
        priority = 50

    normalized = PromptOption(
        id=option_id,
        name=str(item.get("name") or option_id).strip(),
        scope=str(item.get("scope") or scope).strip() or scope,
        capability=capability,
        category=category,
        slot=slot,
        content=str(item.get("content") or "").strip(),
        enabled=_normalize_bool(item.get("enabled"), True),
        built_in=_normalize_bool(item.get("built_in"), built_in),
        priority=priority,
        source=str(item.get("source") or "manual").strip() or "manual",
        source_kind=str(item.get("source_kind") or "").strip(),
        source_ref=str(item.get("source_ref") or "").strip(),
        tags=item.get("tags") or [],
        created_at=str(item.get("created_at") or timestamp),
        updated_at=str(item.get("updated_at") or timestamp),
    ).model_dump()
    return normalized


def normalize_prompt_options_payload(payload: Any, *, scope: str = "story", built_in: bool = False) -> list[dict]:
    raw_items = payload.get("options", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            continue
        option = normalize_prompt_option(item, scope=scope, built_in=built_in, fallback_id=f"option_{index + 1}")
        if option["id"] in seen:
            continue
        seen.add(option["id"])
        normalized.append(option)
    return normalized


def builtin_prompt_options() -> list[dict]:
    return normalize_prompt_options_payload(BUILTIN_PROMPT_OPTIONS, scope="builtin", built_in=True)


def merge_prompt_option_layers(
    global_options: list[dict] | None = None,
    project_options: list[dict] | None = None,
    story_options: list[dict] | None = None,
    *,
    include_builtin: bool = True,
) -> list[dict]:
    merged: dict[str, dict] = {}
    layers: list[tuple[str, list[dict], bool]] = []
    if include_builtin:
        layers.append(("builtin", builtin_prompt_options(), True))
    layers.extend([
        ("global", normalize_prompt_options_payload(global_options or [], scope="global"), False),
        ("project", normalize_prompt_options_payload(project_options or [], scope="project"), False),
        ("story", normalize_prompt_options_payload(story_options or [], scope="story"), False),
    ])

    for scope, items, built_in in layers:
        for item in items:
            normalized = normalize_prompt_option(item, scope=scope, built_in=built_in)
            normalized["scope"] = scope
            normalized["built_in"] = built_in
            merged[normalized["id"]] = normalized

    return sorted(merged.values(), key=lambda item: (int(item.get("priority", 50)), item.get("name", ""), item.get("id", "")))


def filter_prompt_options(
    options: list[dict],
    capability: str,
    *,
    enabled_only: bool = True,
    selected_ids: list[str] | None = None,
) -> list[dict]:
    selected_set = {str(item) for item in selected_ids} if selected_ids is not None else None
    filtered = []
    for option in options:
        if selected_set is None and enabled_only and not option.get("enabled", True):
            continue
        if selected_set is not None and option.get("id") not in selected_set:
            continue
        option_capability = str(option.get("capability") or "")
        if option_capability not in {capability, "all"}:
            continue
        if not str(option.get("content") or "").strip():
            continue
        filtered.append(option)
    return sorted(filtered, key=lambda item: (int(item.get("priority", 50)), item.get("name", ""), item.get("id", "")))


def format_prompt_options_for_prompt(
    options: list[dict],
    capability: str,
    *,
    selected_ids: list[str] | None = None,
) -> str:
    active_options = filter_prompt_options(options, capability, selected_ids=selected_ids)
    if not active_options:
        return ""

    lines = [
        "可配置 Prompt 选项：",
        "以下选项来自内置预设或用户自定义内容，只能影响创作偏好、规划方法、审稿标准或执行策略；不得覆盖存储格式、结构化输出格式和系统硬性要求。",
    ]
    for option in active_options:
        category_label = PROMPT_OPTION_CATEGORIES.get(option.get("category", ""), option.get("category", ""))
        slot_label = PROMPT_OPTION_SLOTS.get(option.get("slot", ""), option.get("slot", ""))
        source = option.get("scope", "")
        lines.append("")
        lines.append(f"【{category_label} / {slot_label} / {source}】{option.get('name', option.get('id', ''))}")
        lines.append(str(option.get("content") or "").strip())
    return "\n".join(lines).strip()


def load_prompt_options(path: str | Path) -> list[dict]:
    file_path = Path(path)
    if not file_path.exists():
        return []
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return normalize_prompt_options_payload(payload)


def save_prompt_options(path: str | Path, options: list[dict]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_prompt_options_payload(options)
    file_path.write_text(
        json.dumps({"options": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def upsert_prompt_option_in_list(options: list[dict], option: dict, *, scope: str = "story") -> list[dict]:
    normalized = normalize_prompt_option(option, scope=scope)
    result = []
    replaced = False
    for item in normalize_prompt_options_payload(options, scope=scope):
        if item.get("id") == normalized["id"]:
            result.append(normalized)
            replaced = True
        else:
            result.append(item)
    if not replaced:
        result.append(normalized)
    return sorted(result, key=lambda item: (int(item.get("priority", 50)), item.get("name", ""), item.get("id", "")))


def delete_prompt_option_from_list(options: list[dict], option_id: str, *, scope: str = "story") -> list[dict]:
    target_id = str(option_id or "").strip()
    return [
        item
        for item in normalize_prompt_options_payload(options, scope=scope)
        if item.get("id") != target_id
    ]


def _string_list(values: Any) -> list[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    result = []
    for value in values:
        text = str(value or "").strip()
        if text:
            result.append(text)
    return result


def _option_lines(options: Any) -> list[str]:
    if not isinstance(options, list):
        return []
    lines = []
    for index, option in enumerate(options, start=1):
        if not isinstance(option, dict):
            continue
        title = str(option.get("title") or f"方案 {index}").strip()
        summary = str(option.get("summary") or "").strip()
        strengths = _string_list(option.get("strengths"))
        risks = _string_list(option.get("risks"))
        line = f"{index}. {title}"
        if summary:
            line += f"：{summary}"
        if strengths:
            line += f"；优势：{'、'.join(strengths[:3])}"
        if risks:
            line += f"；风险：{'、'.join(risks[:3])}"
        lines.append(line)
    return lines


def _discussion_payload(discussion_step: dict) -> dict:
    if not isinstance(discussion_step, dict):
        return {}
    if isinstance(discussion_step.get("discussion"), dict):
        return discussion_step["discussion"]
    if any(key in discussion_step for key in {
        "current_understanding",
        "core_goals",
        "key_constraints",
        "recommended_direction",
        "recommended_profile",
        "options",
        "risks",
    }):
        return discussion_step
    data = discussion_step.get("data", {})
    if not isinstance(data, dict):
        return {}
    discussion = data.get("discussion", {})
    return discussion if isinstance(discussion, dict) else {}


def _discussion_common_content(discussion: dict) -> str:
    parts: list[str] = []
    title = str(discussion.get("title") or "").strip()
    if title:
        parts.append(f"讨论主题：{title}")
    for label, key in [
        ("当前理解", "current_understanding"),
        ("章节目标", "chapter_goal"),
        ("分卷目标", "volume_goal"),
        ("剧情段目标", "arc_goal"),
        ("推荐方向", "recommended_direction"),
    ]:
        value = str(discussion.get(key) or "").strip()
        if value:
            parts.append(f"{label}：{value}")
    constraints = _string_list(discussion.get("key_constraints"))
    if constraints:
        parts.append("关键约束：" + "、".join(constraints[:8]))
    goals = _string_list(discussion.get("core_goals"))
    if goals:
        parts.append("核心目标：" + "、".join(goals[:8]))
    options = _option_lines(discussion.get("options"))
    if options:
        parts.append("可选方向：\n" + "\n".join(options[:4]))
    return "\n".join(parts).strip()


def build_discussion_prompt_option_candidates(
    discussion_step: dict,
    discussion_kind: str,
    *,
    source_ref: str = "",
) -> list[dict]:
    discussion = _discussion_payload(discussion_step)
    if not discussion:
        return []

    base_content = _discussion_common_content(discussion)
    if not base_content:
        return []

    kind = str(discussion_kind or "discussion").strip()
    digest = hashlib.md5(f"{kind}|{source_ref}|{base_content}".encode("utf-8")).hexdigest()[:10]
    title = str(discussion.get("title") or "讨论结论").strip()

    capability_map = {
        "creative_profile": "all",
        "outline": "outline",
        "volume": "outline",
        "arc": "outline",
        "chapter": "chapter_outline",
    }
    capability = capability_map.get(kind, "all")
    candidates = [
        normalize_prompt_option(
            {
                "id": f"discussion_{kind}_planning_{digest}",
                "name": f"{title}：规划提示",
                "capability": capability,
                "category": "planning_method",
                "slot": "planning_guidance",
                "content": base_content,
                "enabled": True,
                "priority": 30,
                "source": "discussion",
                "source_kind": kind,
                "source_ref": source_ref,
                "tags": ["discussion", kind],
            },
            scope="story",
        )
    ]

    if kind in {"creative_profile", "chapter"}:
        write_content = base_content
        profile = discussion.get("recommended_profile")
        if isinstance(profile, dict) and profile:
            profile_lines = []
            for label, key in [
                ("任务性质", "story_mode"),
                ("目标篇幅", "target_length"),
                ("生成层级", "workflow_depth"),
                ("参考强度", "reference_strength"),
                ("冲突策略", "conflict_policy"),
                ("自由说明", "notes"),
            ]:
                value = profile.get(key)
                if isinstance(value, list):
                    value = "、".join(str(item) for item in value if str(item).strip())
                value = str(value or "").strip()
                if value:
                    profile_lines.append(f"{label}：{value}")
            if profile_lines:
                write_content = f"{base_content}\n\n创作配置摘要：\n" + "\n".join(profile_lines)

        candidates.append(
            normalize_prompt_option(
                {
                    "id": f"discussion_{kind}_write_{digest}",
                    "name": f"{title}：写作提示",
                    "capability": "write",
                    "category": "writing_style",
                    "slot": "execution_guidance",
                    "content": write_content,
                    "enabled": True,
                    "priority": 30,
                    "source": "discussion",
                    "source_kind": kind,
                    "source_ref": source_ref,
                    "tags": ["discussion", kind, "write"],
                },
                scope="story",
            )
        )

    risks = _string_list(discussion.get("risks"))
    if risks:
        candidates.append(
            normalize_prompt_option(
                {
                    "id": f"discussion_{kind}_review_{digest}",
                    "name": f"{title}：审稿关注点",
                    "capability": "review",
                    "category": "review_rubric",
                    "slot": "review_criteria",
                    "content": "审稿时重点检查以下风险是否被妥善处理：\n" + "\n".join(f"- {item}" for item in risks),
                    "enabled": True,
                    "priority": 35,
                    "source": "discussion",
                    "source_kind": kind,
                    "source_ref": source_ref,
                    "tags": ["discussion", kind, "review"],
                },
                scope="story",
            )
        )

    return candidates
