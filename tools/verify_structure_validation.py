"""Verify deterministic chapter allocation conflict validation."""

from __future__ import annotations

from tools.verify_utils import isolated_workspace


def main() -> None:
    with isolated_workspace("novelforge_structure_"):
        from novelforge.domain.structure_validation import validate_arc_chapter_plan
        from novelforge.services import memory

        project = memory.create_project("structure-demo")
        story = memory.list_stories(project)[0]["story_id"]
        memory.save_arc_metadata(project, 1, {"estimated_chapter_count": 1, "title": "第一段"}, story)
        memory.save_arc_metadata(project, 2, {"estimated_chapter_count": 1, "title": "第二段"}, story)
        memory.save_arc_outline(project, 1, "第一段大纲", story)
        memory.save_arc_outline(project, 2, "第二段大纲", story)
        memory.save_arc_chapter_plan(project, 2, {"chapters": [{"chapter_no": 2, "title": "重叠"}]}, "", story)
        result = validate_arc_chapter_plan(project, story, 1, {"chapters": [{"chapter_no": 2}, {"chapter_no": 2}]})
        assert result["valid"] is False
        codes = {item["code"] for item in result["conflicts"]}
        assert {"duplicate_chapter", "chapter_count_mismatch", "cross_arc_overlap"}.issubset(codes)
    print("structure validation verification: ok")


if __name__ == "__main__":
    main()
