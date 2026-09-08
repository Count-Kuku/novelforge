"""Implementation slice for the memory facade: chapter and review content."""

from __future__ import annotations

import hashlib
import re

from novelforge.services import memory as _memory_api


def _branch_context(project_name: str, story_id: str, branch_id: str | None, *, writing: bool = False) -> dict | None:
    """Validate branch ownership and write policy, including legacy main calls."""
    clean_branch_id = str(branch_id or _memory_api.default_branch_id(story_id)).strip()
    branch = _memory_api.load_story_branch(project_name, story_id, clean_branch_id)
    if writing and str(branch.get("status") or "active") == "archived":
        raise ValueError("已归档的世界线不能写入章节。")
    if writing and clean_branch_id != _memory_api.default_branch_id(story_id):
        mode = _memory_api.get_story_creation_mode(project_name, story_id)
        if mode == "planned":
            raise ValueError("规划工作台暂不支持非主线章节写入，请切换到对话工作台。")
    return branch


def _branch_folder(branch_id: str) -> str:
    clean = str(branch_id or "").strip()
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", clean)
    return f"{slug[:48]}_{hashlib.sha256(clean.encode('utf-8')).hexdigest()[:12]}"


def _chapter_root(project_name: str, story_id: str, branch_id: str | None = None):
    base = _memory_api._story_path_from_project_path(project_name, story_id)
    if not branch_id or branch_id == _memory_api.default_branch_id(story_id):
        return base
    return base / "branches" / _branch_folder(branch_id)


def _asset_key(branch_id: str | None, story_id: str, logical_key: str) -> str:
    if not branch_id or branch_id == _memory_api.default_branch_id(story_id):
        return logical_key
    return f"branch:{branch_id}:{logical_key}"


def _asset_metadata(branch_id: str | None, story_id: str, chapter_no: int) -> dict:
    return {"chapter_no": chapter_no, "branch_id": branch_id or _memory_api.default_branch_id(story_id)}

def _chapter_outline_meta_path(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> _memory_api.Path:
    path = _chapter_root(project_name, story_id, branch_id) / "chapter_outlines"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.meta.json"


def _chapter_discussion_path(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> _memory_api.Path:
    path = _chapter_root(project_name, story_id, branch_id) / "chapter_outlines"
    path.mkdir(parents=True, exist_ok=True)
    return path / f"chapter_{chapter_no:03d}.discussion.json"


def save_chapter_outline(project_name: str, chapter_no: int, outline: str, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    path = _chapter_root(project_name, story_id, branch_id) / "chapter_outlines"
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(outline, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="chapter_outline",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Outline",
        mime_type="text/markdown",
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_chapter_outline_metadata(project_name: str, chapter_no: int, metadata: dict, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    normalized = _memory_api.ChapterOutlineMetadata.model_validate({**metadata, "chapter_no": chapter_no})
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id, branch_id=branch_id)
    payload = normalized.model_dump()
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="chapter_outline_metadata",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Outline Metadata",
        mime_type="application/json",
        payload=payload,
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_chapter_discussion_artifact(project_name: str, chapter_no: int, discussion: dict, report_markdown: str, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id, branch_id=branch_id)
    payload = {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="chapter_discussion",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Discussion",
        mime_type="application/json",
        payload=payload,
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> dict:
    _branch_context(project_name, story_id, branch_id)
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_discussion",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id, branch_id=branch_id)
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
                logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
                story_id=story_id,
                title=f"Chapter {chapter_no:03d} Discussion",
                payload=payload,
                metadata=_asset_metadata(branch_id, story_id, chapter_no),
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "chapter_no": chapter_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_chapter_discussion_artifact(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> bool:
    _branch_context(project_name, story_id, branch_id, writing=True)
    file = _chapter_discussion_path(project_name, chapter_no, story_id=story_id, branch_id=branch_id)
    logical_key = _asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}")
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


def load_chapter_outline_metadata(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> dict:
    _branch_context(project_name, story_id, branch_id)
    file = _chapter_outline_meta_path(project_name, chapter_no, story_id=story_id, branch_id=branch_id)
    fallback = _memory_api.ChapterOutlineMetadata(chapter_no=chapter_no).model_dump()
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="chapter_outline_metadata",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
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
            logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Outline Metadata",
            payload=normalized,
            metadata=_asset_metadata(branch_id, story_id, chapter_no),
        )
        return normalized
    except Exception:
        return fallback


def load_chapter_outline(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> str:
    _branch_context(project_name, story_id, branch_id)
    file = _chapter_root(project_name, story_id, branch_id) / "chapter_outlines" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_chapter(project_name: str, chapter_no: int, content: str, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    path = _chapter_root(project_name, story_id, branch_id) / "chapters"
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="chapter",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d}",
        mime_type="text/markdown",
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_chapter(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> str:
    _branch_context(project_name, story_id, branch_id)
    file = _chapter_root(project_name, story_id, branch_id) / "chapters" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_review(project_name: str, chapter_no: int, content: str, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    path = _chapter_root(project_name, story_id, branch_id) / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="review_markdown",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Review",
        mime_type="text/markdown",
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_review(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> str:
    _branch_context(project_name, story_id, branch_id)
    file = _chapter_root(project_name, story_id, branch_id) / "reviews" / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


DEFAULT_SUMMARY_LIMIT = 5


def save_branch_chapter_summaries(project_name: str, story_id: str, summaries: list[dict], branch_id: str | None = None) -> None:
    _branch_context(project_name, story_id, branch_id, writing=True)
    if not branch_id or branch_id == _memory_api.default_branch_id(story_id):
        _memory_api.save_story_chapter_summaries(project_name, story_id, summaries)
        return
    path = _chapter_root(project_name, story_id, branch_id) / "chapter_summaries.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = [item for item in list(summaries or []) if isinstance(item, dict)]
    path.write_text(_memory_api.json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="chapter_summaries",
        logical_key=_asset_key(branch_id, story_id, "chapter_summaries"),
        story_id=story_id,
        title="Branch Chapter Summaries",
        payload=normalized,
        metadata={"branch_id": branch_id},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def delete_branch_chapter_summaries(project_name: str, story_id: str, branch_id: str | None = None) -> bool:
    _branch_context(project_name, story_id, branch_id, writing=True)
    if not branch_id or branch_id == _memory_api.default_branch_id(story_id):
        return False
    path = _chapter_root(project_name, story_id, branch_id) / "chapter_summaries.json"
    logical_key = _asset_key(branch_id, story_id, "chapter_summaries")
    existed = path.exists() or _memory_api._asset_payload_exists(project_name, asset_type="chapter_summaries", logical_key=logical_key, story_id=story_id)
    if path.exists():
        path.unlink()
    if existed:
        _memory_api.mark_asset_deleted_record(project_name, asset_type="chapter_summaries", logical_key=logical_key, story_id=story_id)
        _memory_api.sync_project_retrieval_assets(project_name)
    return bool(existed)

def list_branch_chapter_inventory(project_name: str, story_id: str = "default", branch_id: str | None = None) -> list[dict]:
    """List chapter assets in one branch; the legacy main branch keeps its old layout."""
    _branch_context(project_name, story_id, branch_id)
    base = _chapter_root(project_name, story_id, branch_id)
    numbers: set[int] = set()
    for folder in ("chapter_outlines", "chapters", "reviews"):
        directory = base / folder
        if not directory.exists():
            continue
        for file in directory.glob("chapter_*.md"):
            match = re.search(r"chapter_(\d+)", file.name)
            if match:
                numbers.add(int(match.group(1)))
        for file in directory.glob("chapter_*.json"):
            match = re.search(r"chapter_(\d+)", file.name)
            if match:
                numbers.add(int(match.group(1)))
    expected_branch = branch_id or _memory_api.default_branch_id(story_id)
    for record in (
        *_memory_api.list_asset_records(project_name, asset_type="chapter", story_id=story_id),
        *_memory_api.list_asset_records(project_name, asset_type="chapter_outline", story_id=story_id),
    ):
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        record_branch = str(metadata.get("branch_id") or _memory_api.default_branch_id(story_id))
        expected_key = _asset_key(branch_id, story_id, "chapter_")
        if record_branch == expected_branch and str(record.get("logical_key") or "").startswith(expected_key):
            match = re.search(r"chapter_(\d+)", str(record.get("logical_key") or ""))
            if match:
                numbers.add(int(match.group(1)))
    inventory: list[dict] = []
    for chapter_no in sorted(numbers):
        content = load_chapter(project_name, chapter_no, story_id, branch_id)
        outline = load_chapter_outline(project_name, chapter_no, story_id, branch_id)
        review = load_review(project_name, chapter_no, story_id, branch_id)
        inventory.append({
            "chapter_no": chapter_no,
            "metadata": load_chapter_outline_metadata(project_name, chapter_no, story_id, branch_id),
            "has_outline": bool(outline),
            "has_content": bool(content),
            "has_review_markdown": bool(review),
            "has_review_json": load_review_json(project_name, chapter_no, story_id, branch_id) is not None,
            "has_evaluation": False,
            "run_count": 0,
            "updated_at": "",
            "outline_preview": outline[:900],
            "content_preview": content[:900],
            "review_preview": review[:900],
            "review_payload": load_review_json(project_name, chapter_no, story_id, branch_id) or {},
            "evaluation_preview": "",
            "evaluation_payload": {},
        })
    return inventory


def delete_branch_chapter_content(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> bool:
    _branch_context(project_name, story_id, branch_id, writing=True)
    path = _chapter_root(project_name, story_id, branch_id) / "chapters" / f"chapter_{chapter_no:03d}.md"
    logical_key = _asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}")
    existed = path.exists() or _memory_api._asset_record_exists(project_name, asset_type="chapter", logical_key=logical_key, story_id=story_id)
    if path.exists():
        path.unlink()
    if existed:
        _memory_api.mark_asset_deleted_record(project_name, asset_type="chapter", logical_key=logical_key, story_id=story_id)
        _memory_api.sync_project_retrieval_assets(project_name)
    return bool(existed)


def get_recent_chapter_summaries(project_name: str, limit: int = DEFAULT_SUMMARY_LIMIT, story_id: str = "default", branch_id: str | None = None) -> list[dict]:
    _branch_context(project_name, story_id, branch_id)
    if branch_id and branch_id != _memory_api.default_branch_id(story_id):
        payload = _memory_api._load_asset_payload_from_db_best_effort(project_name, asset_type="chapter_summaries", logical_key=_asset_key(branch_id, story_id, "chapter_summaries"), story_id=story_id)
        if isinstance(payload, list):
            summaries = payload
        else:
            path = _chapter_root(project_name, story_id, branch_id) / "chapter_summaries.json"
            try:
                raw = _memory_api.json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            except Exception:
                raw = []
            summaries = raw if isinstance(raw, list) else []
    else:
        summaries = _memory_api.load_story_chapter_summaries(project_name, story_id)
    summaries = [
        item for item in summaries
        if isinstance(item, dict) and item.get("summary")
    ]
    summaries.sort(key=lambda item: item.get("chapter_no", 0))
    return summaries[-limit:]


def save_review_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default", branch_id: str | None = None):
    _branch_context(project_name, story_id, branch_id, writing=True)
    path = _chapter_root(project_name, story_id, branch_id) / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"chapter_{chapter_no:03d}.json"
    payload = data if isinstance(data, dict) else {}
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="review_json",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Review JSON",
        mime_type="application/json",
        payload=payload,
        metadata=_asset_metadata(branch_id, story_id, chapter_no),
    )
    _memory_api.sync_project_retrieval_assets(project_name)

def load_review_json(project_name: str, chapter_no: int, story_id: str = "default", branch_id: str | None = None) -> dict | None:
    _branch_context(project_name, story_id, branch_id)
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="review_json",
        logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        return db_payload
    file = _chapter_root(project_name, story_id, branch_id) / "reviews" / f"chapter_{chapter_no:03d}.json"
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
            logical_key=_asset_key(branch_id, story_id, f"chapter_{chapter_no:03d}"),
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Review JSON",
            payload=payload,
            metadata=_asset_metadata(branch_id, story_id, chapter_no),
        )
        return payload
    except Exception:
        return None
