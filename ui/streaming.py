"""Streaming preview helpers for Streamlit generation actions."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import streamlit as st


LOGGER = logging.getLogger("novelforge.ui.streaming")


JSON_FIELD_LABELS = {
    "title": "标题",
    "assistant_message": "回复",
    "current_understanding": "当前理解",
    "chapter_goal": "章节目标",
    "volume_goal": "分卷目标",
    "arc_goal": "剧情段目标",
    "core_goals": "核心目标",
    "key_constraints": "关键约束",
    "open_questions": "待确认问题",
    "risks": "风险提醒",
    "recommended_direction": "推荐方向",
    "options": "可选方案",
    "recommended_profile": "推荐创作配置",
    "approval_ready": "是否已收敛",
}

PROFILE_FIELD_LABELS = {
    "story_mode": "任务性质",
    "target_length": "目标篇幅",
    "target_word_count": "目标字数",
    "workflow_depth": "生成层级",
    "reference_strength": "资料参考强度",
    "reference_focus": "重点参考方向",
    "allow_canon_deviation": "允许改写原设",
    "conflict_policy": "资料冲突处理",
    "worldline_id": "世界线 ID",
    "worldline_label": "当前世界线",
    "worldline_retrieval_mode": "世界线检索模式",
}


class GenerationCancelled(RuntimeError):
    cancel_generation = True


def _decode_json_string_fragment(value: str) -> str:
    return (
        value
        .replace(r"\\", "\\")
        .replace(r"\"", '"')
        .replace(r"\n", "\n")
        .replace(r"\r", "\r")
        .replace(r"\t", "\t")
    )


def _parse_json_string_at(text: str, start: int) -> tuple[str, int, bool]:
    if start >= len(text) or text[start] != '"':
        return "", start, False

    result: list[str] = []
    index = start + 1
    while index < len(text):
        char = text[index]
        if char == '"':
            return "".join(result), index + 1, True
        if char != "\\":
            result.append(char)
            index += 1
            continue

        if index + 1 >= len(text):
            return "".join(result), len(text), False
        escaped = text[index + 1]
        if escaped == "u":
            token = text[index + 2:index + 6]
            if len(token) < 4 or not re.fullmatch(r"[0-9a-fA-F]{4}", token):
                return "".join(result), len(text), False
            result.append(chr(int(token, 16)))
            index += 6
            continue
        result.append(_decode_json_string_fragment("\\" + escaped))
        index += 2

    return "".join(result), len(text), False


def _skip_json_ws(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _extract_json_candidate(text: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    object_start = cleaned.find("{")
    array_start = cleaned.find("[")
    starts = [item for item in [object_start, array_start] if item >= 0]
    if not starts:
        return cleaned
    return cleaned[min(starts):]


def _find_top_level_value_start(text: str, key: str) -> int | None:
    index = 0
    depth = 0
    in_string = False
    escape = False

    while index < len(text):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            if depth == 1:
                field_name, end_index, complete = _parse_json_string_at(text, index)
                if complete:
                    colon_index = _skip_json_ws(text, end_index)
                    if colon_index < len(text) and text[colon_index] == ":":
                        if field_name == key:
                            return _skip_json_ws(text, colon_index + 1)
                        index = colon_index + 1
                        continue
                    index = end_index
                    continue
            in_string = True
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
        index += 1
    return None


def _find_balanced_json_span(text: str, start: int) -> tuple[int, int, bool]:
    if start >= len(text) or text[start] not in "{[":
        return start, start, False

    stack: list[str] = []
    in_string = False
    escape = False
    index = start
    while index < len(text):
        char = text[index]
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            stack.append("}")
        elif char == "[":
            stack.append("]")
        elif char in "}]":
            if not stack or stack[-1] != char:
                return start, index + 1, False
            stack.pop()
            if not stack:
                return start, index + 1, True
        index += 1

    return start, len(text), False


def _extract_json_value(text: str, key: str) -> tuple[Any, bool]:
    start = _find_top_level_value_start(text, key)
    if start is None or start >= len(text):
        return None, False

    char = text[start]
    if char == '"':
        value, _, complete = _parse_json_string_at(text, start)
        return value, complete
    if char in "{[":
        _, end, complete = _find_balanced_json_span(text, start)
        if not complete:
            return None, False
        try:
            return json.loads(text[start:end]), True
        except json.JSONDecodeError:
            return None, False

    fragment = text[start:start + 16].strip().lower()
    if fragment.startswith("true"):
        return True, True
    if fragment.startswith("false"):
        return False, True
    if fragment.startswith("null"):
        return None, True
    return None, False


def _extract_object_fragment(text: str, key: str) -> str:
    start = _find_top_level_value_start(text, key)
    if start is None or start >= len(text) or text[start] != "{":
        return ""
    _, end, _ = _find_balanced_json_span(text, start)
    return text[start:end]


def _extract_string_list_fragment(text: str, key: str) -> list[str]:
    start = _find_top_level_value_start(text, key)
    if start is None or start >= len(text) or text[start] != "[":
        return []

    value, complete = _extract_json_value(text, key)
    if complete and isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    _, end, _ = _find_balanced_json_span(text, start)
    fragment = text[start:end]
    values: list[str] = []
    depth = 0
    index = 0
    while index < len(fragment):
        char = fragment[index]
        if char == "[":
            depth += 1
            index += 1
            continue
        if char == "]":
            depth = max(0, depth - 1)
            index += 1
            continue
        if char == '"' and depth == 1:
            value, next_index, _ = _parse_json_string_at(fragment, index)
            if value.strip():
                values.append(value.strip())
            index = max(next_index, index + 1)
            continue
        index += 1
    return values


def _extract_object_list_fragment(text: str, key: str) -> list[dict]:
    start = _find_top_level_value_start(text, key)
    if start is None or start >= len(text) or text[start] != "[":
        return []

    value, complete = _extract_json_value(text, key)
    if complete and isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]

    _, end, _ = _find_balanced_json_span(text, start)
    fragment = text[start:end]
    items: list[dict] = []
    depth = 0
    index = 0
    while index < len(fragment):
        char = fragment[index]
        if char == "[":
            depth += 1
            index += 1
            continue
        if char == "]":
            depth = max(0, depth - 1)
            index += 1
            continue
        if char == "{" and depth == 1:
            _, object_end, object_complete = _find_balanced_json_span(fragment, index)
            if not object_complete:
                break
            try:
                item = json.loads(fragment[index:object_end])
            except json.JSONDecodeError:
                index += 1
                continue
            if isinstance(item, dict):
                items.append(item)
            index = object_end
            continue
        index += 1
    return items


def _format_markdown_list(values: list[Any]) -> list[str]:
    return [f"- {str(item).strip()}" for item in values if str(item).strip()]


def _format_discussion_option(option: dict, index: int) -> list[str]:
    title = str(option.get("title", "") or "").strip() or f"方案 {index}"
    lines = [f"#### {index}. {title}"]
    summary = str(option.get("summary", "") or "").strip()
    if summary:
        lines.extend(["", summary])
    strengths = option.get("strengths", [])
    if isinstance(strengths, list) and strengths:
        lines.extend(["", "**优点**"])
        lines.extend(_format_markdown_list(strengths))
    risks = option.get("risks", [])
    if isinstance(risks, list) and risks:
        lines.extend(["", "**风险**"])
        lines.extend(_format_markdown_list(risks))
    return lines


def _format_profile_preview(profile: dict) -> list[str]:
    lines: list[str] = []
    for field, label in PROFILE_FIELD_LABELS.items():
        if field not in profile:
            continue
        value = profile.get(field)
        if isinstance(value, list):
            text = "、".join(str(item) for item in value if str(item).strip())
        elif isinstance(value, bool):
            text = "是" if value else "否"
        else:
            text = str(value or "").strip()
        if text:
            lines.append(f"- **{label}**：{text}")
    return lines


def _format_json_stream_preview(text: str, *, cursor: bool = False) -> str:
    candidate = _extract_json_candidate(text)
    if not candidate:
        return "正在等待模型开始输出..."

    parsed: dict[str, Any] | None = None
    try:
        loaded = json.loads(candidate)
        if isinstance(loaded, dict):
            parsed = loaded
    except json.JSONDecodeError:
        parsed = None

    discussion_data = None
    if isinstance(parsed, dict) and isinstance(parsed.get("discussion"), dict):
        discussion_data = parsed["discussion"]
    discussion_fragment = _extract_object_fragment(candidate, "discussion")
    content_data = discussion_data if discussion_data is not None else parsed
    content_text = discussion_fragment or candidate

    lines: list[str] = []
    title_value = content_data.get("title") if isinstance(content_data, dict) else _extract_json_value(content_text, "title")[0]
    title = str(title_value or "").strip()
    lines.append(f"### {title or '正在生成结构化内容'}")

    assistant_message = parsed.get("assistant_message") if parsed else _extract_json_value(candidate, "assistant_message")[0]
    assistant_message = str(assistant_message or "").strip()
    if assistant_message:
        lines.extend(["", f"#### {JSON_FIELD_LABELS['assistant_message']}", "", assistant_message])

    string_fields = [
        "chapter_goal",
        "volume_goal",
        "arc_goal",
        "current_understanding",
        "recommended_direction",
    ]
    for field in string_fields:
        value = content_data.get(field) if isinstance(content_data, dict) else _extract_json_value(content_text, field)[0]
        value = str(value or "").strip()
        if value:
            lines.extend(["", f"#### {JSON_FIELD_LABELS[field]}", "", value])

    list_fields = ["core_goals", "key_constraints", "open_questions", "risks"]
    for field in list_fields:
        values = content_data.get(field) if isinstance(content_data, dict) else _extract_string_list_fragment(content_text, field)
        if not isinstance(values, list):
            continue
        formatted_values = _format_markdown_list(values)
        if formatted_values:
            lines.extend(["", f"#### {JSON_FIELD_LABELS[field]}"])
            lines.extend(formatted_values)

    options = content_data.get("options") if isinstance(content_data, dict) else _extract_object_list_fragment(content_text, "options")
    if isinstance(options, list) and options:
        lines.extend(["", "#### 可选方案"])
        for index, option in enumerate([item for item in options if isinstance(item, dict)], start=1):
            lines.extend(["", *_format_discussion_option(option, index)])

    profile = content_data.get("recommended_profile") if isinstance(content_data, dict) else _extract_json_value(content_text, "recommended_profile")[0]
    if isinstance(profile, dict):
        formatted_profile = _format_profile_preview(profile)
        if formatted_profile:
            lines.extend(["", "#### 推荐创作配置"])
            lines.extend(formatted_profile)

    approval_ready = content_data.get("approval_ready") if isinstance(content_data, dict) else _extract_json_value(content_text, "approval_ready")[0]
    if isinstance(approval_ready, bool):
        lines.extend(["", f"**是否已收敛**：{'是' if approval_ready else '否'}"])

    if len(lines) == 1:
        lines.extend(["", "正在接收结构化内容，解析到完整字段后会逐段显示。"])
    if cursor:
        lines.append("\n▌")
    return "\n".join(lines)


def render_stream_preview(preview_slot, text: str, preview_language: str | None = None, *, cursor: bool = False):
    preview_text = text or "等待模型开始输出..."
    if preview_language == "json":
        preview_slot.markdown(_format_json_stream_preview(text, cursor=cursor))
    elif preview_language:
        if cursor:
            preview_text = f"{preview_text}\n\n▌"
        preview_slot.code(preview_text, language=preview_language)
    else:
        if cursor:
            preview_text = f"{preview_text}▌"
        preview_slot.markdown(preview_text)


def safe_stream_emit(stream_callback, text: str):
    if not stream_callback:
        return
    try:
        stream_callback(text)
    except Exception as exc:
        if getattr(exc, "cancel_generation", False):
            raise
        LOGGER.warning("Stream callback failed while emitting marker: %s", exc, exc_info=True)


def make_stream_preview(label: str, preview_language: str | None = None, stream_container=None):
    host = stream_container or st
    status = host.status(label, expanded=True)
    with status:
        preview_slot = st.empty()
        render_stream_preview(preview_slot, "", preview_language)
    state = {"text": "", "last_render_len": 0}

    def stream_callback(delta: str):
        if not delta:
            return
        delta_text = str(delta)
        state["text"] += delta_text
        if preview_language == "json":
            text_len = len(state["text"])
            should_render = text_len - state["last_render_len"] >= 120 or any(char in delta_text for char in "\n,}]")
            if not should_render:
                return
            state["last_render_len"] = text_len
        render_stream_preview(preview_slot, state["text"], preview_language, cursor=True)

    def complete(message: str = "生成完成。"):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="complete", expanded=False)

    def cancel(message: str = "生成已中止。"):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="complete", expanded=True)

    def fail(message: str):
        render_stream_preview(preview_slot, state["text"], preview_language)
        status.update(label=message, state="error", expanded=True)

    return stream_callback, complete, cancel, fail


def run_with_stream(label: str, func, *args, preview_language: str | None = None, stream_container=None, **kwargs):
    stream_callback, complete, cancel, fail = make_stream_preview(
        label,
        preview_language=preview_language,
        stream_container=stream_container,
    )
    try:
        result = func(*args, stream_callback=stream_callback, **kwargs)
        complete()
        return result
    except GenerationCancelled:
        cancel()
        st.stop()
    except Exception as exc:
        fail(f"{label}失败：{exc}")
        raise
