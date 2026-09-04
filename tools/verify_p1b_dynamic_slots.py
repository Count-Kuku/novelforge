"""Verify P1b: dynamic slot field definitions + extraction slot expansion.

Asserts:
- characters/locations/organizations gain status (and characters gains location/holding);
- a dict candidate carrying `name` + dynamic-slot keys expands into one item per slot
  with fact_key = slot (so same-slot supersession can fire);
- string candidates and slotless dicts keep the legacy single-item behaviour.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.domain.knowledge_types import KNOWLEDGE_TYPE_FIELDS
from novelforge.workflows.skills.common import (
    DYNAMIC_SLOT_KEYS,
    build_pending_knowledge_from_setting_extraction,
)

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


def field_keys(category: str) -> set[str]:
    return {f.key for f in KNOWLEDGE_TYPE_FIELDS[category]}


def main() -> int:
    print("=== P1b 动态槽位补齐 ===\n")

    print("[1] 字段定义补齐")
    check("characters 补 location", "location" in field_keys("characters"))
    check("characters 补 status", "status" in field_keys("characters"))
    check("characters 补 holding", "holding" in field_keys("characters"))
    check("locations 补 status", "status" in field_keys("locations"))
    check("organizations 补 status", "status" in field_keys("organizations"))
    check("items 原本有 status", "status" in field_keys("items"))

    print("\n[2] 动态槽位展开")
    update = {
        "new_characters": [
            {"name": "林越", "location": "京城", "status": "受伤", "holding": "青霜剑"},
        ],
        "timeline_updates": [],
        "world_updates": [],
        "foreshadowing_updates": [],
    }
    items = build_pending_knowledge_from_setting_extraction(update, "s1", 5)
    by_fact = {i.get("setting_field"): i for i in items}
    check("展开为 3 个槽位条目", len(items) == 3, f"got {len(items)}")
    check("有 location 槽位", "location" in by_fact)
    check("有 status 槽位", "status" in by_fact)
    check("有 holding 槽位", "holding" in by_fact)
    check("条目 name 为角色名", all(i.get("name") == "林越" for i in items))
    check("fact_key 为细粒度槽位（非大类）", all(i.get("setting_field") in DYNAMIC_SLOT_KEYS for i in items))
    check("summary 含实体名与值", by_fact.get("location", {}).get("summary") == "林越：京城")

    print("\n[3] 无槽位对象保持原行为")
    update2 = {
        "new_characters": [{"name": "林越", "motivations": "复仇"}],  # motivations 非动态槽位
        "timeline_updates": [],
        "world_updates": [],
        "foreshadowing_updates": [],
    }
    items2 = build_pending_knowledge_from_setting_extraction(update2, "s1", 5)
    check("无动态槽位 → 单条目", len(items2) == 1, f"got {len(items2)}")

    print("\n[4] 字符串候选保持原行为")
    update3 = {
        "new_characters": ["林越出场"],
        "timeline_updates": [],
        "world_updates": [],
        "foreshadowing_updates": [],
    }
    items3 = build_pending_knowledge_from_setting_extraction(update3, "s1", 5)
    check("字符串 → 单条目", len(items3) == 1, f"got {len(items3)}")
    check("字符串条目 fact_key 为大类", items3[0].get("setting_field") == "characters")

    print("\n[5] 不同章节同槽位可产生可取代的 fact_key")
    update4 = {
        "new_characters": [{"name": "林越", "location": "洛阳"}],
        "timeline_updates": [],
        "world_updates": [],
        "foreshadowing_updates": [],
    }
    items4 = build_pending_knowledge_from_setting_extraction(update4, "s1", 8)
    check("第8章 location 槽位 fact_key=location", items4[0].get("setting_field") == "location")
    check("第5章与第8章同 name+fact_key（可取代）",
          items[0].get("name") == items4[0].get("name")
          and items[0].get("setting_field") == items4[0].get("setting_field"))

    print("\n[6] append 类槽位也展开")
    update5 = {
        "new_characters": [{"name": "林越", "appearance": "脸上添疤", "personality": "愈发坚毅"}],
        "timeline_updates": [],
        "world_updates": [],
        "foreshadowing_updates": [],
    }
    items5 = build_pending_knowledge_from_setting_extraction(update5, "s1", 20)
    fk = {i.get("setting_field") for i in items5}
    check("appearance 展开", "appearance" in fk)
    check("personality 展开", "personality" in fk)
    check("append 槽位数量=2", len(items5) == 2, f"got {len(items5)}")

    print(f"\n结果：{_PASS} 通过，{_FAIL} 失败")
    return 1 if _FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
