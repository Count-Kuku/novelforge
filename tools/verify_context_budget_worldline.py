"""Verify refactor 2 · P2: budget allocation by capability + arc worldline + temporal validator.

1. 预算：`_retrieval_reserve_ratio_for` 按 capability 给出检索 floor 比例（write 0.30 /
   outline 0.20）；实体识别激活时上调；显式 None 默认保持 0.25 语义不回归。
2. 世界线：章节所属 arc 元数据可提供 worldline（D6），profile 显式优先；
   arc worldline 持久化 roundtrip。
3. 时序矛盾校验器：正常 supersede 半开区间无警告；重叠（前条未关即开新值）报警。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "0"

from novelforge.core.schemas import ContextBlock
from novelforge.domain.setting_knowledge import validate_temporal_conflicts
from novelforge.services.memory import (
    create_project,
    create_story,
    load_arc_metadata,
    save_arc_metadata,
    save_chapter_outline_metadata,
)
from novelforge.workflows.context_assembly import (
    _apply_context_budget,
    _resolve_worldline_id,
    _retrieval_reserve_ratio_for,
)
from tools.verify_utils import isolated_workspace

_PASS = 0
_FAIL = 0


def check(label: str, ok: bool, detail: str = ""):
    global _PASS, _FAIL
    if ok:
        _PASS += 1
        print(f"  PASS  {label}")
    else:
        _FAIL += 1
        print(f"  FAIL  {label}  {detail}")


def main() -> int:
    print("=== Refactor2 P2 · 预算 + 世界线 + 时序校验 ===\n")

    print("[1] 预算 floor 比例（capability 画像，D7）")
    check("write=0.30", abs(_retrieval_reserve_ratio_for("write") - 0.30) < 1e-6, str(_retrieval_reserve_ratio_for("write")))
    check("outline=0.20", abs(_retrieval_reserve_ratio_for("outline") - 0.20) < 1e-6, str(_retrieval_reserve_ratio_for("outline")))
    check("默认=0.25", abs(_retrieval_reserve_ratio_for("unknown_cap") - 0.25) < 1e-6, str(_retrieval_reserve_ratio_for("unknown_cap")))
    active_ratio = _retrieval_reserve_ratio_for("write", entity_plan_active=True, entity_count=3)
    check("实体识别激活时 floor 提升", active_ratio > 0.30 - 1e-6 and active_ratio <= 1.0, str(active_ratio))

    # 默认（None）与显式 0.25 行为一致 → 不回归既有预算语义
    def _block(block_id, category, tokens, hard=False, priority=50):
        return ContextBlock(block_id=block_id, category=category, content="x" * max(tokens, 1),
                            source_type="test", placement="reference", priority=priority,
                            hard_constraint=hard, estimated_tokens=tokens)

    blocks = [
        _block("always", "always_settings", 2000, hard=True, priority=900),
        _block("rules", "rules", 500, hard=True, priority=1000),
        _block("ret1", "retrieval", 900, priority=40),
        _block("ret2", "retrieval", 900, priority=40),
        _block("opt", "generation_guidance", 400, priority=100),
    ]
    inc_none, _, _, _ = _apply_context_budget(blocks, 4000)
    inc_default, _, _, _ = _apply_context_budget(blocks, 4000, retrieval_reserve_ratio=None)
    inc_explicit, _, _, _ = _apply_context_budget(blocks, 4000, retrieval_reserve_ratio=0.25)
    none_ids = sorted(b.block_id for b in inc_none)
    check("默认 None 与显式 0.25 结果一致", none_ids == sorted(b.block_id for b in inc_explicit), str(none_ids))
    check("None 等价旧语义（0.25 保留部分检索）", any(b.category == "retrieval" for b in inc_default), str(none_ids))

    print("\n[2] arc worldline 解析（D6）")
    with isolated_workspace("novelforge_p2_wl_"):
        project_name = create_project("p2-worldline")
        story_id = str(create_story(project_name, "主线").get("story_id") or "default")
        save_arc_metadata(project_name, 1, {"title": "青云卷", "worldline_id": "au2", "worldline_label": "AU-2"}, story_id)
        roundtrip = load_arc_metadata(project_name, 1, story_id)
        check("arc worldline roundtrip", str(roundtrip.get("worldline_id")) == "au2", str(roundtrip.get("worldline_id")))
        save_chapter_outline_metadata(project_name, 7, {"arc_no": 1}, story_id)
        resolved = _resolve_worldline_id(project_name, story_id, 7, "")
        check("章节→arc→worldline 解析", resolved == "au2", resolved)
        # profile 显式优先
        resolved_profile = _resolve_worldline_id(project_name, story_id, 7, "main")
        check("profile 显式优先于 arc", resolved_profile == "main", resolved_profile)
        # 无章节 arc 关联 → 空
        empty_resolved = _resolve_worldline_id(project_name, story_id, 99, "")
        check("无 arc 关联时回退空(下游回 main)", empty_resolved == "", empty_resolved)

    print("\n[3] 时序矛盾校验器")
    normal = [
        {"canonical_name": "林越", "setting_field": "location", "valid_from_chapter": 5, "valid_to_chapter": 8, "knowledge_id": "a"},
        {"canonical_name": "林越", "setting_field": "location", "valid_from_chapter": 8, "valid_to_chapter": None, "knowledge_id": "b"},
    ]
    check("正常 supersede 半开区间无警告", validate_temporal_conflicts(normal) == [], str(validate_temporal_conflicts(normal)))
    overlapped = [
        {"canonical_name": "林越", "setting_field": "location", "valid_from_chapter": 5, "valid_to_chapter": 9, "knowledge_id": "a"},
        {"canonical_name": "林越", "setting_field": "location", "valid_from_chapter": 8, "valid_to_chapter": None, "knowledge_id": "b"},
    ]
    warns = validate_temporal_conflicts(overlapped)
    check("重叠区间被检出", len(warns) == 1 and "重叠" in warns[0], str(warns))

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
