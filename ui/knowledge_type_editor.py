"""Category-aware knowledge fields for Streamlit forms."""
from __future__ import annotations

import streamlit as st

from novelforge.domain.knowledge_types import (
    KNOWLEDGE_TYPE_FIELDS,
    normalize_typed_knowledge_item,
)


def render_typed_knowledge_fields(category: str, item: dict) -> dict:
    fields = KNOWLEDGE_TYPE_FIELDS.get(str(category or ""), ())
    if not fields:
        return {}
    normalized = normalize_typed_knowledge_item(item, category)
    typed_data = normalized.get("typed_data", {})
    st.markdown("##### 分类专属字段")
    st.caption("这些字段会以稳定结构保存，供筛选、聚合和检索使用；详情 JSON 仍会完整保留。")
    all_known_keys = {
        field.key
        for category_fields in KNOWLEDGE_TYPE_FIELDS.values()
        for field in category_fields
    }
    target_keys = {field.key for field in fields}
    # Preserve extension fields but discard fields that belong exclusively to
    # the previous category when a user moves an item between categories.
    result: dict = {
        key: value
        for key, value in typed_data.items()
        if key not in all_known_keys or key in target_keys
    }
    for field in fields:
        label = f"{field.label}{' *' if field.required else ''}"
        current = typed_data.get(field.key, [] if field.kind == "list" else "")
        if field.kind == "list":
            value = st.text_area(
                label,
                value="\n".join(str(item) for item in current) if isinstance(current, list) else str(current or ""),
                height=82,
                help="每行一项，也可使用顿号或分号分隔。",
            )
            result[field.key] = [
                part.strip()
                for line in value.replace("；", "\n").replace(";", "\n").splitlines()
                for part in line.split("、")
                if part.strip()
            ]
        else:
            result[field.key] = st.text_input(label, value=str(current or ""))
    return result
