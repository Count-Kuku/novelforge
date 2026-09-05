"""Implementation slice for the memory facade: outline/volume/arc content."""

from __future__ import annotations

from novelforge.services import memory as _memory_api

def save_outline(project_name: str, outline: str, story_id: str = "default"):
    path = _memory_api._story_path_from_project_path(project_name, story_id, "outline.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(outline, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        path,
        asset_type="outline",
        logical_key="main",
        story_id=story_id,
        title="Story Outline",
        mime_type="text/markdown",
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_outline(project_name: str, story_id: str = "default") -> str:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "outline.md")
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _outline_discussion_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    return _memory_api._story_path_from_project_path(project_name, story_id, "outline.discussion.json")


def save_outline_discussion_artifact(project_name: str, discussion: dict, report_markdown: str, story_id: str = "default"):
    path = _outline_discussion_path(project_name, story_id)
    payload = {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        path,
        asset_type="outline_discussion",
        logical_key="main",
        story_id=story_id,
        title="Story Outline Discussion",
        mime_type="application/json",
        payload=payload,
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_outline_discussion_artifact(project_name: str, story_id: str = "default") -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="outline_discussion",
        logical_key="main",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    path = _outline_discussion_path(project_name, story_id)
    if payload is None and not path.exists():
        return {}
    if payload is None:
        try:
            payload = _memory_api.json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if isinstance(payload, dict):
            _memory_api._sync_asset_payload_to_db_best_effort(
                project_name,
                path,
                asset_type="outline_discussion",
                logical_key="main",
                story_id=story_id,
                title="Story Outline Discussion",
                payload=payload,
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_outline_discussion_artifact(project_name: str, story_id: str = "default") -> bool:
    path = _outline_discussion_path(project_name, story_id)
    existed = path.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="outline_discussion",
        logical_key="main",
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        path.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="outline_discussion",
        logical_key="main",
        story_id=story_id,
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return True


def volumes_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "volumes")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _volume_markdown_path(project_name: str, volume_no: int, story_id: str = "default") -> _memory_api.Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.md"


def _volume_meta_path(project_name: str, volume_no: int, story_id: str = "default") -> _memory_api.Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.meta.json"


def _volume_discussion_path(project_name: str, volume_no: int, story_id: str = "default") -> _memory_api.Path:
    return volumes_path(project_name, story_id) / f"volume_{volume_no:03d}.discussion.json"


def arcs_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "arcs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def _arc_markdown_path(project_name: str, arc_no: int, story_id: str = "default") -> _memory_api.Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.md"


def _arc_meta_path(project_name: str, arc_no: int, story_id: str = "default") -> _memory_api.Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.meta.json"


def _arc_discussion_path(project_name: str, arc_no: int, story_id: str = "default") -> _memory_api.Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.discussion.json"


def _arc_chapter_plan_path(project_name: str, arc_no: int, story_id: str = "default") -> _memory_api.Path:
    return arcs_path(project_name, story_id) / f"arc_{arc_no:03d}.chapter_plan.json"


def save_volume_outline(project_name: str, volume_no: int, outline: str, story_id: str = "default"):
    file = _volume_markdown_path(project_name, volume_no, story_id)
    file.write_text(outline, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="volume_outline",
        logical_key=f"volume_{volume_no:03d}",
        story_id=story_id,
        title=f"Volume {volume_no:03d} Outline",
        mime_type="text/markdown",
        metadata={"volume_no": volume_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_volume_outline(project_name: str, volume_no: int, story_id: str = "default") -> str:
    file = _volume_markdown_path(project_name, volume_no, story_id)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_volume_metadata(project_name: str, volume_no: int, metadata: dict, story_id: str = "default"):
    current = load_volume_metadata(project_name, volume_no, story_id)
    normalized = _memory_api.VolumeOutlineMetadata.model_validate({**current, **metadata, "volume_no": volume_no})
    file = _volume_meta_path(project_name, volume_no, story_id)
    payload = normalized.model_dump()
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="volume_metadata",
        logical_key=f"volume_{volume_no:03d}",
        story_id=story_id,
        title=f"Volume {volume_no:03d} Metadata",
        mime_type="application/json",
        payload=payload,
        metadata={"volume_no": volume_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_volume_discussion_artifact(project_name: str, volume_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _volume_discussion_path(project_name, volume_no, story_id)
    payload = {
        "volume_no": volume_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="volume_discussion",
        logical_key=f"volume_{volume_no:03d}",
        story_id=story_id,
        title=f"Volume {volume_no:03d} Discussion",
        mime_type="application/json",
        payload=payload,
        metadata={"volume_no": volume_no},
    )
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))}, story_id)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_volume_discussion_artifact(project_name: str, volume_no: int, story_id: str = "default") -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="volume_discussion",
        logical_key=f"volume_{volume_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    file = _volume_discussion_path(project_name, volume_no, story_id)
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
                asset_type="volume_discussion",
                logical_key=f"volume_{volume_no:03d}",
                story_id=story_id,
                title=f"Volume {volume_no:03d} Discussion",
                payload=payload,
                metadata={"volume_no": volume_no},
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "volume_no": volume_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_volume_discussion_artifact(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    file = _volume_discussion_path(project_name, volume_no, story_id)
    logical_key = f"volume_{volume_no:03d}"
    existed = file.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="volume_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        file.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="volume_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    save_volume_metadata(project_name, volume_no, {"has_approved_discussion": False}, story_id)
    _memory_api.sync_project_retrieval_assets(project_name)
    return True


def load_volume_metadata(project_name: str, volume_no: int, story_id: str = "default") -> dict:
    file = _volume_meta_path(project_name, volume_no, story_id)
    fallback = _memory_api.VolumeOutlineMetadata(volume_no=volume_no).model_dump()
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="volume_metadata",
        logical_key=f"volume_{volume_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        try:
            return _memory_api.VolumeOutlineMetadata.model_validate(db_payload).model_dump()
        except Exception:
            pass
    if not file.exists():
        return fallback
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        normalized = _memory_api.VolumeOutlineMetadata.model_validate(payload).model_dump()
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="volume_metadata",
            logical_key=f"volume_{volume_no:03d}",
            story_id=story_id,
            title=f"Volume {volume_no:03d} Metadata",
            payload=normalized,
            metadata={"volume_no": volume_no},
        )
        return normalized
    except Exception:
        return fallback


def list_volumes(project_name: str, story_id: str = "default") -> list[dict]:
    path = volumes_path(project_name, story_id)
    volume_numbers: set[int] = set()
    for record in [
        *_memory_api.list_asset_records(project_name, asset_type="volume_outline", story_id=story_id),
        *_memory_api.list_asset_payload_records(project_name, asset_type="volume_metadata", story_id=story_id),
        *_memory_api.list_asset_payload_records(project_name, asset_type="volume_discussion", story_id=story_id),
    ]:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        try:
            value = metadata.get("volume_no")
            if value is not None:
                volume_numbers.add(int(value))
                continue
        except (TypeError, ValueError):
            pass
        match = _memory_api.re.search(r"volume_(\d+)", str(record.get("logical_key") or record.get("relative_path") or ""))
        if match:
            volume_numbers.add(int(match.group(1)))
    for file in path.glob("volume_*.md"):
        try:
            volume_numbers.add(int(file.stem.split("_")[-1]))
        except Exception:
            continue
    for file in path.glob("volume_*.meta.json"):
        try:
            volume_numbers.add(int(file.name.replace("volume_", "").replace(".meta.json", "")))
        except Exception:
            continue

    items = []
    for volume_no in sorted(volume_numbers):
        metadata = load_volume_metadata(project_name, volume_no, story_id)
        outline = load_volume_outline(project_name, volume_no, story_id)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_volume(project_name: str, volume_no: int, story_id: str = "default") -> bool:
    deleted = False
    logical_key = f"volume_{volume_no:03d}"
    markdown_path = _volume_markdown_path(project_name, volume_no, story_id)
    meta_path = _volume_meta_path(project_name, volume_no, story_id)
    discussion_path = _volume_discussion_path(project_name, volume_no, story_id)
    markdown_existed = markdown_path.exists()
    meta_existed = meta_path.exists()
    discussion_existed = discussion_path.exists()
    if markdown_existed:
        markdown_path.unlink()
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="volume_outline",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if meta_existed:
        meta_path.unlink()
        deleted = True
    if meta_existed or _memory_api._asset_payload_exists(project_name, asset_type="volume_metadata", logical_key=logical_key, story_id=story_id):
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="volume_metadata",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if discussion_existed:
        discussion_path.unlink()
        deleted = True
    if discussion_existed or _memory_api._asset_payload_exists(project_name, asset_type="volume_discussion", logical_key=logical_key, story_id=story_id):
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="volume_discussion",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if deleted:
        chapter_outline_dir = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines")
        if chapter_outline_dir.exists():
            for file in chapter_outline_dir.glob("chapter_*.meta.json"):
                try:
                    payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    normalized = _memory_api.ChapterOutlineMetadata.model_validate(payload).model_dump()
                except Exception:
                    continue
                if normalized.get("volume_no") != volume_no:
                    continue
                normalized["volume_no"] = None
                if normalized.get("arc_no") is not None:
                    normalized["arc_no"] = None
                chapter_no = int(normalized.get("chapter_no") or file.name.replace("chapter_", "").replace(".meta.json", ""))
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
    if deleted:
        _memory_api.sync_project_retrieval_assets(project_name)
    return deleted


def save_arc_outline(project_name: str, arc_no: int, outline: str, story_id: str = "default"):
    file = _arc_markdown_path(project_name, arc_no, story_id)
    file.write_text(outline, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="arc_outline",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
        title=f"Arc {arc_no:03d} Outline",
        mime_type="text/markdown",
        metadata={"arc_no": arc_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_arc_outline(project_name: str, arc_no: int, story_id: str = "default") -> str:
    file = _arc_markdown_path(project_name, arc_no, story_id)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def save_arc_metadata(project_name: str, arc_no: int, metadata: dict, story_id: str = "default"):
    current = load_arc_metadata(project_name, arc_no, story_id)
    normalized = _memory_api.ArcOutlineMetadata.model_validate({**current, **metadata, "arc_no": arc_no})
    file = _arc_meta_path(project_name, arc_no, story_id)
    payload = normalized.model_dump()
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="arc_metadata",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
        title=f"Arc {arc_no:03d} Metadata",
        mime_type="application/json",
        payload=payload,
        metadata={"arc_no": arc_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_arc_discussion_artifact(project_name: str, arc_no: int, discussion: dict, report_markdown: str, story_id: str = "default"):
    file = _arc_discussion_path(project_name, arc_no, story_id)
    payload = {
        "arc_no": arc_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="arc_discussion",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
        title=f"Arc {arc_no:03d} Discussion",
        mime_type="application/json",
        payload=payload,
        metadata={"arc_no": arc_no},
    )
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": bool((discussion or {}).get("approval_ready"))}, story_id)
    _memory_api.sync_project_retrieval_assets(project_name)


def load_arc_discussion_artifact(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="arc_discussion",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    file = _arc_discussion_path(project_name, arc_no, story_id)
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
                asset_type="arc_discussion",
                logical_key=f"arc_{arc_no:03d}",
                story_id=story_id,
                title=f"Arc {arc_no:03d} Discussion",
                payload=payload,
                metadata={"arc_no": arc_no},
            )
    if not isinstance(payload, dict):
        return {}
    discussion = payload.get("discussion", {})
    return {
        "arc_no": arc_no,
        "discussion": discussion if isinstance(discussion, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_arc_discussion_artifact(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    file = _arc_discussion_path(project_name, arc_no, story_id)
    logical_key = f"arc_{arc_no:03d}"
    existed = file.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="arc_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        file.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="arc_discussion",
        logical_key=logical_key,
        story_id=story_id,
    )
    save_arc_metadata(project_name, arc_no, {"has_approved_discussion": False}, story_id)
    _memory_api.sync_project_retrieval_assets(project_name)
    return True


def save_arc_chapter_plan(project_name: str, arc_no: int, plan: dict, report_markdown: str, story_id: str = "default"):
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
    payload = {
        "arc_no": arc_no,
        "plan": plan if isinstance(plan, dict) else {},
        "report_markdown": str(report_markdown or ""),
    }
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="arc_chapter_plan",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
        title=f"Arc {arc_no:03d} Chapter Plan",
        mime_type="application/json",
        payload=payload,
        metadata={"arc_no": arc_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_arc_chapter_plan(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="arc_chapter_plan",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        payload = db_payload
    else:
        payload = None
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
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
                asset_type="arc_chapter_plan",
                logical_key=f"arc_{arc_no:03d}",
                story_id=story_id,
                title=f"Arc {arc_no:03d} Chapter Plan",
                payload=payload,
                metadata={"arc_no": arc_no},
            )
    if not isinstance(payload, dict):
        return {}
    plan = payload.get("plan", {})
    return {
        "arc_no": arc_no,
        "plan": plan if isinstance(plan, dict) else {},
        "report_markdown": str(payload.get("report_markdown", "") or ""),
    }


def delete_arc_chapter_plan(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    file = _arc_chapter_plan_path(project_name, arc_no, story_id)
    logical_key = f"arc_{arc_no:03d}"
    existed = file.exists()
    exists_in_db = _memory_api._asset_payload_exists(
        project_name,
        asset_type="arc_chapter_plan",
        logical_key=logical_key,
        story_id=story_id,
    )
    if not existed and not exists_in_db:
        return False
    if existed:
        file.unlink()
    _memory_api.mark_asset_deleted_record(
        project_name,
        asset_type="arc_chapter_plan",
        logical_key=logical_key,
        story_id=story_id,
    )
    _memory_api.sync_project_retrieval_assets(project_name)
    return True


def load_arc_metadata(project_name: str, arc_no: int, story_id: str = "default") -> dict:
    file = _arc_meta_path(project_name, arc_no, story_id)
    fallback = _memory_api.ArcOutlineMetadata(arc_no=arc_no).model_dump()
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="arc_metadata",
        logical_key=f"arc_{arc_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        try:
            return _memory_api.ArcOutlineMetadata.model_validate(db_payload).model_dump()
        except Exception:
            pass
    if not file.exists():
        return fallback
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        normalized = _memory_api.ArcOutlineMetadata.model_validate(payload).model_dump()
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="arc_metadata",
            logical_key=f"arc_{arc_no:03d}",
            story_id=story_id,
            title=f"Arc {arc_no:03d} Metadata",
            payload=normalized,
            metadata={"arc_no": arc_no},
        )
        return normalized
    except Exception:
        return fallback


def list_arcs(project_name: str, volume_no: int | None = None, story_id: str = "default") -> list[dict]:
    path = arcs_path(project_name, story_id)
    arc_numbers: set[int] = set()
    for record in [
        *_memory_api.list_asset_records(project_name, asset_type="arc_outline", story_id=story_id),
        *_memory_api.list_asset_payload_records(project_name, asset_type="arc_metadata", story_id=story_id),
        *_memory_api.list_asset_payload_records(project_name, asset_type="arc_discussion", story_id=story_id),
        *_memory_api.list_asset_payload_records(project_name, asset_type="arc_chapter_plan", story_id=story_id),
    ]:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        try:
            value = metadata.get("arc_no")
            if value is not None:
                arc_numbers.add(int(value))
                continue
        except (TypeError, ValueError):
            pass
        match = _memory_api.re.search(r"arc_(\d+)", str(record.get("logical_key") or record.get("relative_path") or ""))
        if match:
            arc_numbers.add(int(match.group(1)))
    for file in path.glob("arc_*.md"):
        try:
            arc_numbers.add(int(file.stem.split("_")[-1]))
        except Exception:
            continue
    for file in path.glob("arc_*.meta.json"):
        try:
            arc_numbers.add(int(file.name.replace("arc_", "").replace(".meta.json", "")))
        except Exception:
            continue

    items = []
    for arc_no in sorted(arc_numbers):
        metadata = load_arc_metadata(project_name, arc_no, story_id)
        if volume_no is not None and metadata.get("volume_no") != volume_no:
            continue
        outline = load_arc_outline(project_name, arc_no, story_id)
        items.append({
            **metadata,
            "outline": outline,
            "has_outline": bool(outline.strip()),
        })
    return items


def delete_arc(project_name: str, arc_no: int, story_id: str = "default") -> bool:
    deleted = False
    logical_key = f"arc_{arc_no:03d}"
    markdown_path = _arc_markdown_path(project_name, arc_no, story_id)
    meta_path = _arc_meta_path(project_name, arc_no, story_id)
    discussion_path = _arc_discussion_path(project_name, arc_no, story_id)
    chapter_plan_path = _arc_chapter_plan_path(project_name, arc_no, story_id)
    markdown_existed = markdown_path.exists()
    meta_existed = meta_path.exists()
    discussion_existed = discussion_path.exists()
    chapter_plan_existed = chapter_plan_path.exists()
    if markdown_existed:
        markdown_path.unlink()
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="arc_outline",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if meta_existed:
        meta_path.unlink()
        deleted = True
    if meta_existed or _memory_api._asset_payload_exists(project_name, asset_type="arc_metadata", logical_key=logical_key, story_id=story_id):
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="arc_metadata",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if discussion_existed:
        discussion_path.unlink()
        deleted = True
    if discussion_existed or _memory_api._asset_payload_exists(project_name, asset_type="arc_discussion", logical_key=logical_key, story_id=story_id):
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="arc_discussion",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if chapter_plan_existed:
        chapter_plan_path.unlink()
        deleted = True
    if chapter_plan_existed or _memory_api._asset_payload_exists(project_name, asset_type="arc_chapter_plan", logical_key=logical_key, story_id=story_id):
        _memory_api.mark_asset_deleted_record(
            project_name,
            asset_type="arc_chapter_plan",
            logical_key=logical_key,
            story_id=story_id,
        )
        deleted = True
    if deleted:
        chapter_outline_dir = _memory_api._story_path_from_project_path(project_name, story_id, "chapter_outlines")
        if chapter_outline_dir.exists():
            for file in chapter_outline_dir.glob("chapter_*.meta.json"):
                try:
                    payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
                    normalized = _memory_api.ChapterOutlineMetadata.model_validate(payload).model_dump()
                except Exception:
                    continue
                if normalized.get("arc_no") != arc_no:
                    continue
                normalized["arc_no"] = None
                chapter_no = int(normalized.get("chapter_no") or file.name.replace("chapter_", "").replace(".meta.json", ""))
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
    if deleted:
        _memory_api.sync_project_retrieval_assets(project_name)
    return deleted
