"""Verify story creation modes across SQLite, JSON mirrors, and story APIs."""

from __future__ import annotations

from pathlib import Path

from tools.verify_utils import isolated_workspace


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    from novelforge.services import memory
    from novelforge.services.memory import create_project, create_story, copy_story, list_stories
    from novelforge.workflows.context_assembly import assemble_generation_context
    from novelforge.workflows.interactive_writing import create_writing_session
    from storage.db import inspect_project_db

    with isolated_workspace("novelforge_creation_modes_"):
        project_name = create_project("mode-check")

        default_story = list_stories(project_name)[0]
        _assert(default_story["story_id"] == "default", "默认故事 ID 不正确")
        _assert(default_story["creation_mode"] == "planned", "旧故事默认模式必须为 planned")
        _assert(memory.get_story_creation_mode(project_name) == "planned", "默认故事模式读取失败")

        conversational = create_story(
            project_name,
            "即时讨论",
            description="不经过规划的轻量创作",
            creation_mode="conversational",
        )
        _assert(conversational["creation_mode"] == "conversational", "创建对话故事未保存模式")
        _assert(memory.get_story_creation_mode(project_name, conversational["story_id"]) == "conversational", "对话模式读取失败")

        outline_path = memory.story_path(project_name, conversational["story_id"]) / "outline.md"
        memory.save_outline(project_name, "# 不应因切换模式丢失的资产", story_id=conversational["story_id"])
        _assert(outline_path.exists(), "测试资产未创建")

        changed = memory.set_story_creation_mode(project_name, conversational["story_id"], "planned")
        _assert(changed["creation_mode"] == "planned", "模式切换未返回 planned")
        _assert(memory.get_story_creation_mode(project_name, conversational["story_id"]) == "planned", "模式切换未写入 SQLite")
        _assert(outline_path.exists(), "模式切换不应删除故事资产")

        conversational_story = create_story(project_name, "对话上下文", creation_mode="conversational")
        memory.save_outline(project_name, "# 不应自动注入的规划大纲", story_id=conversational_story["story_id"])
        session = create_writing_session(project_name, conversational_story["story_id"], session_goal="测试不依赖规划资产")
        _assert(session["auto_extract_mode"] == "on_accept", "对话故事的新会话应默认开启接受后提炼")
        context = assemble_generation_context(
            project_name,
            story_id=conversational_story["story_id"],
            capability="write",
            query="测试对话上下文",
            retrieval_profile="drafting",
        )
        categories = {block.category for block in context.blocks}
        source_types = {block.source_type for block in context.blocks}
        _assert("creative_profile" not in categories, "对话模式不应自动注入规划创作配置")
        _assert("outline" not in source_types, "对话模式不应自动注入规划大纲")

        copied = copy_story(project_name, conversational["story_id"], "规划副本", include_discussions=False, include_summaries=False, include_chapters=False)
        _assert(copied["creation_mode"] == "planned", "复制故事未继承源故事模式")

        db_info = inspect_project_db(Path("data") / project_name)
        _assert(db_info["schema_version"] == 16, "项目数据库未升级到 schema 16")
        rows = list_stories(project_name)
        _assert({row["creation_mode"] for row in rows} == {"planned", "conversational"}, "故事列表存在未规范化的模式值")

    print("creation modes verification: ok")


if __name__ == "__main__":
    main()
