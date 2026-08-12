from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory import (
    create_project,
    create_story,
    knowledge_revision_diff,
    load_knowledge_category,
    load_knowledge_center_index_state,
    load_knowledge_center_record,
    load_knowledge_revisions,
    process_knowledge_center_index,
    restore_knowledge_revision,
    restore_archived_knowledge_item,
    search_knowledge_center,
    update_confirmed_knowledge_item_record,
    upsert_knowledge_category_item_record,
)
from storage import open_project_db
from storage.repositories import sync_knowledge_category, sync_pending_knowledge
from tools.verify_utils import isolated_workspace


CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def verify_unified_center() -> None:
    with isolated_workspace("novelforge_knowledge_center_"):
        project_name = "knowledge_center_verify"
        create_project(project_name)
        story_id = str(create_story(project_name, "知识中心故事")["story_id"])
        root = Path("data/projects") / project_name
        characters = [
            {
                "id": f"character_{index:05d}",
                "category": "characters",
                "name": f"角色{index:05d}",
                "summary": f"银铃渡口守桥人编号{index:05d}",
                "story_id": story_id if index % 2 else "",
                "worldline_id": "main" if index % 3 else "branch-a",
                "worldline_label": "本项目主线" if index % 3 else "分支甲",
                "status": "confirmed",
            }
            for index in range(6000)
        ]
        rules = [
            {
                "id": f"rule_{index:05d}",
                "category": "world_rules",
                "name": f"潮汐规则{index:05d}",
                "summary": f"旧桥潮汐规则编号{index:05d}",
                "worldline_id": "main",
                "status": "confirmed",
            }
            for index in range(3000)
        ]
        pending = [
            {
                "pending_id": f"pending_{index:05d}",
                "category": "locations",
                "name": f"候选地点{index:05d}",
                "summary": f"雾港候选地点编号{index:05d}",
                "story_id": story_id,
                "worldline_id": "main",
                "status": "pending",
            }
            for index in range(1000)
        ]
        with open_project_db(root) as conn:
            conn.execute("BEGIN IMMEDIATE")
            sync_knowledge_category(conn, "characters", characters)
            sync_knowledge_category(conn, "world_rules", rules)
            sync_pending_knowledge(conn, pending)
            conn.commit()
        check(sum(len(load_knowledge_category(project_name, category)) for category in ("characters", "world_rules")) == 9000, "大型正式知识库写入完成")
        result = process_knowledge_center_index(project_name, limit=2000)
        check(result["processed"] == 2000 and result["remaining"] == 8000, "增量索引任务分页处理且不阻塞整库")
        while result.get("remaining"):
            result = process_knowledge_center_index(project_name, limit=2000)
        check(result.get("failed_total") == 0, "一万条正式/待审核知识增量索引无失败")

        latencies: list[float] = []
        for index in range(60):
            started = time.perf_counter()
            page = search_knowledge_center(
                project_name,
                query=f"守桥人编号{index * 97 % 6000:05d}",
                story_id=story_id,
                page_size=30,
            )
            latencies.append((time.perf_counter() - started) * 1000)
            check(len(page["items"]) <= 30, f"搜索页 {index + 1} 未超出分页上限")
        p95 = statistics.quantiles(latencies, n=20)[18]
        check(p95 < 300.0, f"一万条跨分类 FTS 搜索 p95 小于 300ms（{p95:.1f}ms）")

        all_page = search_knowledge_center(project_name, query="潮汐规则", page_size=25)
        check(all_page["has_more"] and len(all_page["items"]) == 25, "统一搜索返回稳定游标分页")
        second_page = search_knowledge_center(
            project_name, query="潮汐规则", cursor=all_page["next_cursor"], page_size=25,
        )
        check(
            {item["record_id"] for item in all_page["items"]}.isdisjoint(
                {item["record_id"] for item in second_page["items"]}
            ),
            "下一页不重复上一页记录",
        )
        character_page = search_knowledge_center(
            project_name, query="银铃渡口", record_types=["knowledge"], categories=["characters"],
            story_id=story_id, worldline_id="main", page_size=40,
        )
        check(
            character_page["items"] and all(item["category"] == "characters" for item in character_page["items"]),
            "搜索可同时过滤分类、记录类型、故事和世界线",
        )
        pending_page = search_knowledge_center(
            project_name, query="候选地点", record_types=["pending"], page_size=20,
        )
        check(pending_page["items"] and all(item["record_type"] == "pending" for item in pending_page["items"]), "待审核内容纳入统一搜索")
        check(search_knowledge_center(project_name, query="雾港", record_types=["pending"])["items"], "两个汉字的短查询使用受限 LIKE 回退")

        edit_id = "character_00001"
        edit_started = time.perf_counter()
        changed = update_confirmed_knowledge_item_record(
            project_name,
            "characters",
            edit_id,
            {"summary": "银铃渡口的新任守桥人。", "revision_reason": "性能验收编辑"},
            target_category="characters",
        )
        commit_ms = (time.perf_counter() - edit_started) * 1000
        check(changed and commit_ms < 500.0, f"单条保存事务反馈小于 500ms（{commit_ms:.1f}ms）")
        state = load_knowledge_center_index_state(project_name)
        check(state.get("retrieval_status") == "queued", "保存后检索后台更新状态可见")
        immediate = search_knowledge_center(project_name, query="新任守桥人", page_size=10)
        check(any(item["record_id"] == edit_id for item in immediate["items"]), "提交后词法索引增量更新并立即可搜索")

        revisions = load_knowledge_revisions(project_name, edit_id)
        old_revision = next(
            item for item in revisions
            if str(item.get("snapshot", {}).get("summary") or "").startswith("银铃渡口守桥人编号")
        )
        current = load_knowledge_center_record(project_name, "knowledge", edit_id)["payload"]
        check("+  \"summary\"" in knowledge_revision_diff(current, old_revision), "知识历史可生成字段级修订差异")
        restore_knowledge_revision(project_name, edit_id, old_revision["revision_id"])
        restored = load_knowledge_center_record(project_name, "knowledge", edit_id)["payload"]
        check(restored["summary"].startswith("银铃渡口守桥人编号"), "历史内容恢复为新修订而非覆盖历史")
        check(len(load_knowledge_revisions(project_name, edit_id)) > len(revisions), "恢复操作追加新的知识修订")

        upsert_knowledge_category_item_record(
            project_name,
            "characters",
            {"id": "archived_demo", "category": "characters", "name": "归档示例", "summary": "等待归档"},
        )
        update_confirmed_knowledge_item_record(
            project_name, "characters", "archived_demo", {}, delete_only=True,
        )
        archive_page = search_knowledge_center(
            project_name, query="归档示例", archived_only=True, include_archived=True,
        )
        check(any(item["record_id"] == "archived_demo" for item in archive_page["items"]), "软删除知识仍可在归档视图检索")
        restore_archived_knowledge_item(project_name, "archived_demo")
        check(not load_knowledge_center_record(project_name, "knowledge", "archived_demo")["archived"], "归档知识可恢复并保留同一稳定 ID")


def main() -> int:
    try:
        verify_unified_center()
    except Exception as exc:
        print(json.dumps({"ok": False, "checks": CHECKS, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"ok": True, "checks": CHECKS}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
