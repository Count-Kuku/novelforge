"""Deterministic validation for planned structure allocation assets.

The validator deliberately reads through memory/project facades so the API never
reimplements storage paths or mutates a plan while checking it.
"""

from __future__ import annotations

from typing import Any

from novelforge.services import memory, project_manager


def _chapter_rows(plan: dict[str, Any]) -> list[dict[str, Any]]:
    rows = plan.get("chapters") if isinstance(plan, dict) else []
    if not isinstance(rows, list):
        rows = []
    return [row for row in rows if isinstance(row, dict)]


def validate_arc_chapter_plan(project_name: str, story_id: str, arc_no: int, plan: dict[str, Any]) -> dict[str, Any]:
    metadata = memory.load_arc_metadata(project_name, arc_no, story_id)
    rows = _chapter_rows(plan)
    conflicts: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    seen: dict[int, int] = {}
    for index, row in enumerate(rows):
        try:
            chapter_no = int(row.get("chapter_no"))
        except (TypeError, ValueError):
            conflicts.append({"code": "invalid_chapter_no", "index": index, "message": "章节分配缺少有效的 chapter_no。"})
            continue
        if chapter_no < 1:
            conflicts.append({"code": "invalid_chapter_no", "chapter_no": chapter_no, "message": "章节编号必须大于 0。"})
        if chapter_no in seen:
            conflicts.append({"code": "duplicate_chapter", "chapter_no": chapter_no, "message": f"第 {chapter_no} 章在同一剧情段中重复分配。", "indices": [seen[chapter_no], index]})
        else:
            seen[chapter_no] = index
        if not str(row.get("title") or row.get("chapter_goal") or "").strip():
            warnings.append({"code": "missing_chapter_goal", "chapter_no": chapter_no, "message": f"第 {chapter_no} 章尚未填写标题或章节目标。"})

    expected_count = metadata.get("estimated_chapter_count")
    if expected_count is not None:
        try:
            expected = int(expected_count)
            if expected > 0 and len(rows) != expected:
                conflicts.append({"code": "chapter_count_mismatch", "expected": expected, "actual": len(rows), "message": f"剧情段预计 {expected} 章，但当前分配了 {len(rows)} 章。"})
        except (TypeError, ValueError):
            warnings.append({"code": "invalid_estimated_count", "message": "剧情段的预计章节数无法解析。"})

    inventory = project_manager.list_chapter_inventory(project_name, story_id=story_id)
    assigned_elsewhere: dict[int, list[int]] = {}
    for other_arc in memory.list_arcs(project_name, story_id=story_id):
        try:
            other_no = int(other_arc.get("arc_no"))
        except (TypeError, ValueError):
            continue
        other_plan = memory.load_arc_chapter_plan(project_name, other_no, story_id)
        for row in _chapter_rows(other_plan.get("plan", {})):
            try:
                other_chapter = int(row.get("chapter_no"))
            except (TypeError, ValueError):
                continue
            if other_no != int(arc_no):
                assigned_elsewhere.setdefault(other_chapter, []).append(other_no)
    for chapter_no, arc_numbers in assigned_elsewhere.items():
        if chapter_no in seen:
            conflicts.append({"code": "cross_arc_overlap", "chapter_no": chapter_no, "arc_numbers": sorted(set([int(arc_no), *arc_numbers])), "message": f"第 {chapter_no} 章同时分配给多个剧情段，需人工合并。"})

    inventory_map = {int(item.get("chapter_no")): item for item in inventory if str(item.get("chapter_no", "")).isdigit()}
    for chapter_no in seen:
        if chapter_no in inventory_map:
            owner = (inventory_map[chapter_no].get("metadata") or {}) if isinstance(inventory_map[chapter_no], dict) else {}
            owner_arc = owner.get("arc_no")
            if owner_arc not in (None, "", arc_no):
                conflicts.append({"code": "inventory_owner_mismatch", "chapter_no": chapter_no, "owner_arc_no": owner_arc, "message": f"第 {chapter_no} 章已有结构归属，与当前剧情段不一致。"})

    return {
        "valid": not conflicts,
        "status": "passed" if not conflicts else "conflict",
        "arc_no": int(arc_no),
        "chapter_count": len(rows),
        "conflicts": conflicts,
        "warnings": warnings,
        "requires_manual_merge": any(item.get("code") == "cross_arc_overlap" for item in conflicts),
    }
