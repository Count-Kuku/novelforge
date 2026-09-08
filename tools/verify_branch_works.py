"""Verify same-story chapter and Works isolation across worldlines."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from novelforge.services import memory
from novelforge.services.creative_works import list_story_works
from tools.verify_utils import isolated_workspace


def main() -> int:
    failures: list[str] = []
    checks: list[str] = []

    def check(condition: bool, label: str) -> None:
        (checks if condition else failures).append(label)

    with isolated_workspace("novelforge_branch_works_"):
        project = memory.create_project("branch_works")
        story_id = memory.create_story(project, "同章隔离", creation_mode="conversational")["story_id"]
        main_branch = memory.default_branch_id(story_id)
        memory.save_chapter(project, 1, "主线正文", story_id, main_branch)
        child = memory.fork_story_branch(
            project,
            story_id,
            parent_branch_id=main_branch,
            name="分支正文",
            allow_current_state=True,
            create_session=False,
        )["branch"]["branch_id"]
        memory.save_chapter(project, 1, "分支正文", story_id, child)

        check(memory.load_chapter(project, 1, story_id, main_branch) == "主线正文", "主线正文保持可读")
        check(memory.load_chapter(project, 1, story_id, child) == "分支正文", "子线正文独立可读")
        child_works = list_story_works(project, story_id, branch_id=child)
        main_works = list_story_works(project, story_id, branch_id=main_branch)
        check(any(item.get("id") == "chapter:1" and item.get("preview") == "分支正文" for item in child_works["items"]), "作品页按子线读取章节")
        check(any(item.get("id") == "chapter:1" and item.get("preview") == "主线正文" for item in main_works["items"]), "作品页按主线读取章节")
        omitted_works = list_story_works(project, story_id)
        check(any(item.get("id") == "chapter:1" and item.get("preview") == "主线正文" for item in omitted_works["items"]), "省略 branch_id 默认读取主线作品")
        check(not any(item.get("id") == "chapter:1" and item.get("preview") == "分支正文" for item in omitted_works["items"]), "省略 branch_id 不混入子线作品")
        records = memory.list_asset_records(project, asset_type="chapter", story_id=story_id)
        child_record = next((item for item in records if str(item.get("metadata", {}).get("branch_id")) == child), {})
        check(str(child_record.get("metadata", {}).get("branch_id")) == child, "章节资产元数据带 branch_id")

        memory.update_story_branch(project, story_id, child, {"status": "archived"})
        check(memory.load_chapter(project, 1, story_id, child) == "分支正文", "归档线仍可读取正文")
        try:
            memory.save_chapter(project, 1, "不应写入", story_id, child)
        except ValueError:
            check(True, "归档线写入被拒绝")
        else:
            check(False, "归档线写入被拒绝")

        # The legacy positional chapter API must still honor the archived main
        # status if an old database contains that state.
        with memory.open_project_db(memory.project_path(project).resolve()) as conn:
            conn.execute("UPDATE story_branches SET status = 'archived' WHERE branch_id = ?", (main_branch,))
            conn.commit()
        try:
            memory.save_chapter(project, 2, "不应写入归档主线", story_id)
        except ValueError:
            check(True, "省略 branch_id 不能绕过归档主线写入校验")
        else:
            check(False, "省略 branch_id 不能绕过归档主线写入校验")

        planned_story = memory.create_story(project, "规划故事", creation_mode="planned")["story_id"]
        planned_main = memory.default_branch_id(planned_story)
        planned_child = memory.fork_story_branch(project, planned_story, parent_branch_id=planned_main, name="规划分支", allow_current_state=True, create_session=False)["branch"]["branch_id"]
        try:
            memory.save_chapter(project, 1, "不应写入", planned_story, planned_child)
        except ValueError:
            check(True, "规划故事非主线写入被拒绝")
        else:
            check(False, "规划故事非主线写入被拒绝")

    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
