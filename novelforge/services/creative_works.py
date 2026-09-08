"""Read-only projection of accepted prose and saved chapters."""

from __future__ import annotations

from novelforge.services import memory
from novelforge.services.project_manager import list_chapter_inventory


def _validate_branch(project_name: str, story_id: str, branch_id: str | None, *, writing: bool = False) -> None:
    effective_branch_id = str(branch_id or memory.default_branch_id(story_id))
    branch = memory.load_story_branch(project_name, story_id, effective_branch_id)
    if writing and str(branch.get("status") or "active") == "archived":
        raise ValueError("已归档的世界线不能修改作品。")
    if writing and effective_branch_id != memory.default_branch_id(story_id) and memory.get_story_creation_mode(project_name, story_id) == "planned":
        raise ValueError("规划工作台暂不支持非主线作品写入，请切换到对话工作台。")


def _preview(value: object, limit: int = 900) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def list_story_works(
    project_name: str,
    story_id: str,
    *,
    cursor: int = 0,
    page_size: int = 40,
    branch_id: str | None = None,
) -> dict:
    _validate_branch(project_name, story_id, branch_id)
    items: list[dict] = []
    expected_branch = str(branch_id or memory.default_branch_id(story_id))
    for fragment in memory.list_creative_works(project_name, story_id):
        if expected_branch and str(fragment.get("branch_id") or memory.default_branch_id(story_id)) != expected_branch:
            continue
        accepted_at = str(fragment.get("accepted_at") or fragment.get("created_at") or "")
        items.append({
            "id": f"fragment:{fragment.get('fragment_id')}",
            "kind": "conversation_fragment",
            "title": str(fragment.get("session_title") or fragment.get("session_goal") or "对话作品"),
            "subtitle": "已定稿片段" if fragment.get("status") == "finalized" else "已采用片段",
            "preview": _preview(fragment.get("content")),
            "word_count": int(fragment.get("word_count") or len(str(fragment.get("content") or ""))),
            "status": str(fragment.get("status") or "accepted"),
            "updated_at": accepted_at,
            "session_id": str(fragment.get("session_id") or ""),
            "fragment_id": str(fragment.get("fragment_id") or ""),
            "chapter_no": fragment.get("target_chapter_no"),
        })

    chapters = memory.list_branch_chapter_inventory(project_name, story_id=story_id, branch_id=branch_id) if branch_id else list_chapter_inventory(project_name, story_id=story_id)
    for chapter in chapters:
        if not chapter.get("has_content"):
            continue
        chapter_no = int(chapter.get("chapter_no") or 0)
        metadata = chapter.get("metadata") if isinstance(chapter.get("metadata"), dict) else {}
        items.append({
            "id": f"chapter:{chapter_no}",
            "kind": "chapter",
            "title": str(metadata.get("title") or f"第 {chapter_no} 章"),
            "subtitle": "已保存章节",
            "preview": _preview(chapter.get("content_preview")),
            "word_count": len(str(chapter.get("content_preview") or "")),
            "status": "saved",
            "updated_at": str(chapter.get("updated_at") or ""),
            "chapter_no": chapter_no,
        })

    items.sort(key=lambda item: (str(item.get("updated_at") or ""), str(item.get("id") or "")), reverse=True)
    start = max(int(cursor or 0), 0)
    size = max(1, min(int(page_size or 40), 100))
    page = items[start : start + size]
    return {
        "items": page,
        "next_cursor": str(start + size) if start + size < len(items) else "",
        "total": len(items),
    }


def delete_chapter_work(project_name: str, story_id: str, chapter_no: int, branch_id: str | None = None) -> bool:
    """Delete only the saved chapter body represented on the Works page."""
    if int(chapter_no) < 1:
        raise ValueError("章节编号必须大于 0。")
    _validate_branch(project_name, story_id, branch_id, writing=True)
    return memory.delete_branch_chapter_content(project_name, int(chapter_no), story_id=story_id, branch_id=branch_id)


def remove_fragment_work(project_name: str, story_id: str, fragment_id: str, branch_id: str | None = None) -> bool:
    """Remove a prose fragment from Works while preserving its conversation."""
    _validate_branch(project_name, story_id, branch_id, writing=True)
    effective_branch_id = str(branch_id or memory.default_branch_id(story_id))
    return memory.remove_creative_work(project_name, fragment_id, story_id=story_id, branch_id=effective_branch_id)
