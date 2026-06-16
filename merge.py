from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class MergeOption:
    path: str
    label: str
    source_value: Any
    target_value: Any
    conflict: bool
    field_type: str = "scalar"
    resolution: Any = None
    resolution_choice: str | None = None


def build_merge_plan(
    source: dict,
    target: dict,
    source_label: str = "来源",
    target_label: str = "目标",
    base_path: str = "",
) -> list[MergeOption]:
    plan: list[MergeOption] = []

    all_keys = set(source.keys()) | set(target.keys())
    for key in sorted(all_keys):
        path = f"{base_path}.{key}" if base_path else key
        sv = source.get(key)
        tv = target.get(key)

        if isinstance(sv, dict) and isinstance(tv, dict):
            plan.extend(build_merge_plan(sv, tv, source_label, target_label, path))
        elif isinstance(sv, list) and isinstance(tv, list):
            conflict = _list_has_conflict(sv, tv)
            plan.append(MergeOption(
                path=path,
                label=key,
                source_value=list(sv),
                target_value=list(tv),
                conflict=conflict,
                field_type="list",
            ))
        else:
            conflict = sv != tv and sv is not None and tv is not None
            plan.append(MergeOption(
                path=path,
                label=key,
                source_value=sv,
                target_value=tv,
                conflict=conflict,
                field_type="scalar",
            ))

    return plan


def _list_has_conflict(a: list, b: list) -> bool:
    if not a or not b:
        return len(a or []) != len(b or [])
    set_a = {_list_item_key(item) for item in a}
    set_b = {_list_item_key(item) for item in b}
    return set_a != set_b


def _list_item_key(item: Any) -> str:
    if isinstance(item, dict):
        name = item.get("name", "") or item.get("title", "") or ""
        return str(name)
    return str(item).strip()


def _merge_dedup(a: list, b: list) -> list:
    seen: set[str] = set()
    result: list = []
    for item in a + b:
        key = _list_item_key(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result
