from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


class NovelForgeSchema(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _stringify_item(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    if isinstance(value, dict):
        preferred_keys = [
            "summary",
            "content",
            "description",
            "detail",
            "finding",
            "issue",
            "recommendation",
            "title",
            "name",
            "text",
        ]
        for key in preferred_keys:
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()

        parts = []
        for key, item in value.items():
            text = _stringify_item(item)
            if text:
                parts.append(f"{key}: {text}")
        return "; ".join(parts)

    if isinstance(value, list):
        parts = [_stringify_item(item) for item in value]
        return "; ".join(part for part in parts if part)

    return str(value).strip()


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        value = [value]

    normalized = []
    for item in value:
        text = _stringify_item(item)
        if text:
            normalized.append(text)
    return normalized


def _shorten_text(value: str, max_length: int = 40) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _infer_knowledge_item_name(item: dict, index: int) -> str:
    for key in ("name", "title", "subject", "entity", "item", "summary", "content", "description"):
        text = _stringify_item(item.get(key))
        if text:
            return _shorten_text(text)

    details = item.get("details")
    if isinstance(details, dict):
        for key in ("名称", "标题", "对象", "角色", "物品", "能力", "地点", "组织", "事件", "关系"):
            text = _stringify_item(details.get(key))
            if text:
                return _shorten_text(text)
        text = _stringify_item(details)
        if text:
            return _shorten_text(text)

    evidence = item.get("evidence")
    if isinstance(evidence, list):
        for evidence_item in evidence:
            text = _stringify_item(evidence_item)
            if text:
                return _shorten_text(text)

    return f"未命名知识 {index + 1}"


SOURCE_TYPE_LABELS = {
    "external_source": "通用外部资料",
    "external_character_sheet": "角色资料",
    "external_location_sheet": "地点资料",
    "external_organization_sheet": "组织资料",
    "external_timeline_note": "时间线资料",
    "external_canon_event": "原作事件",
    "external_world_rule": "世界规则",
    "external_artifact_note": "道具资料",
}


def _label_source_type(value: str) -> str:
    return SOURCE_TYPE_LABELS.get(str(value or ""), str(value or "未知资料"))
