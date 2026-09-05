"""Implementation slice for the memory facade: chapter and review content."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

def _chapter_outline_meta_path(project_name: str, chapter_no: int, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.meta.json"


def _chapter_discussion_path(project_name: str, chapter_no: int, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.discussion.json"


def save_chapter_outline(project_name: str, chapter_no: int, outline: str, story_id: str = "default"):
    path = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(outline, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="chapter_outline",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Outline",
        mime_type="text/markdown",
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_chapter_outline_metadata(project_name: str, chapter_no: int, metadata: dict, story_id: str = "default"):
    normalized = _memory_api.ChapterOutlineMetadata.model_validate({**metadata, "chapter_no": chapter_no})
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id)
    payload = normalized.model_dump()
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="chapter_outline_metadata",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Outline Metadata",
        mime_type="application/json",
        payload=payload,
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_chapter_discussion_artifact(project_name: str, chapter_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
    payload = {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="chapter_discussion",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Discussion",
        mime_type="application/json",
        payload=payload,
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default") -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_discussion",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
    if payload is None and not file.exists():
        return {}
    if payload is None:
        try:
            payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                file,
                asset_type="chapter_discussion",
                logical_key=f"chapter_{chapter_no:03d}",
                story_id=story_id,
                title=f"Chapter {chapter_no:03d} Discussion",
                payload=payload,
                metadata={"chapter_no": chapter_no},
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id)
    logical_key = f"chapter_{chapter_no:03d}"
    existed = file.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="chapter_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        file.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="chapter_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return True


def load_chapter_outline_metadata(project_name: str, chapter_no: int, story_id: str = "default") -> dict:
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id)
    fallback = _memory_api.ChapterOutlineMetadata(chapter_no=chapter_no).model_dump()
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_outline_metadata",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        try:
            return _memory_api.ChapterOutlineMetadata.model_validate(db_payload).model_dump()
        except Exception:
            pass
    if not file.exists():
        return fallback
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        normalized = _memory_api.ChapterOutlineMetadata.model_validate(payload).model_dump()
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="chapter_outline_metadata",
            logical_key=f"chapter_{chapter_no:03d}",
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Outline Metadata",
            payload=normalized,
            metadata={"chapter_no": chapter_no},
        )
        return normalized
    except Exception:
        return fallback


def load_chapter_outline(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_chapter(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    path = _memory_api._story_path_from_project_path(project_name, story_id, "chapters")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="chapter",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d}",
        mime_type="text/markdown",
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_chapter(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _memory_api._story_path_from_project_path(project_name, story_id, "chapters") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_review(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    path = _memory_api._story_path_from_project_path(project_name, story_id, "reviews")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="review_markdown",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Review",
        mime_type="text/markdown",
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_review(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = _memory_api._story_path_from_project_path(project_name, story_id, "reviews") / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


DEFAULT_SUMMARY_LIMIT = 5

def get_recent_chapter_summaries(project_name: str, limit: int = DEFAULT_SUMMARY_LIMIT, story_id: str = "default") -> list[dict]:
    summaries = _memory_api.load_story_chapter_summaries(project_name, story_id)
    summaries = [
        item for item in summaries
        if isinstance(item, dict) and item.get("summary")
    ]
    summaries.sort(key=lambda item: item.get("chapter_no", 0))
    return summaries[-limit:]


def save_review_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default"):
    path = _memory_api._story_path_from_project_path(project_name, story_id, "reviews")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.json"
    payload = data if isinstance(data, dict) else {}
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="review_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Review JSON",
        mime_type="application/json",
        payload=payload,
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)

def load_review_json(project_name: str, chapter_no: int, story_id: str = "default") -> dict | None:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="review_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        return db_payload
    file = _memory_api._story_path_from_project_path(project_name, story_id, "reviews") / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="review_json",
            logical_key=f"chapter_{chapter_no:03d}",
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Review JSON",
            payload=payload,
            metadata={"chapter_no": chapter_no},
        )
        return payload
    except Exception:
        return None
