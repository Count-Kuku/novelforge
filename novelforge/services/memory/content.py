"""Implementation slice for the memory facade: content."""

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
    _memory_api._write_json_mirror(path, payload)
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
    _memory_api._write_json_mirror(file, payload)
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
    _memory_api._write_json_mirror(file, payload)
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
                _memory_api._write_json_mirror(file, normalized)
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
    _memory_api._write_json_mirror(file, payload)
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
    _memory_api._write_json_mirror(file, payload)
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
    _memory_api._write_json_mirror(file, payload)
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
                _memory_api._write_json_mirror(file, normalized)
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
    _memory_api._write_json_mirror(file, payload)
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
    _memory_api._write_json_mirror(file, payload)
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
    _memory_api._write_json_mirror(file, payload)
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


def upsert_knowledge_category_item_record(project_name: str, category: str, item: dict) -> dict:
    """Atomically upsert one knowledge item without replacing concurrent peers."""

    if category not in _memory_api.KNOWLEDGE_CATEGORIES:
        raise ValueError(f"未知知识分类：{category}")
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        saved, items = _memory_api.upsert_knowledge_category_item(conn, category, item)
        conn.commit()
    _memory_api._refresh_project_json_mirror(project_name, _memory_api.knowledge_category_path(project_name, category), items)
    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return saved


def delete_knowledge_category_item_record(project_name: str, category: str, item_id: str) -> bool:
    """Atomically delete one knowledge item without replacing concurrent peers."""

    if category not in _memory_api.KNOWLEDGE_CATEGORIES:
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        deleted, items = _memory_api.delete_knowledge_category_item(conn, category, item_id)
        conn.commit()
    if deleted:
        _memory_api._refresh_project_json_mirror(project_name, _memory_api.knowledge_category_path(project_name, category), items)
        _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return deleted


def update_confirmed_knowledge_item_record(
    project_name: str,
    original_category: str,
    item_id: str,
    updated_item: dict,
    *,
    target_category: str | None = None,
    delete_only: bool = False,
) -> bool:
    """Atomically update, move, or delete one confirmed knowledge item.

    A category move changes the source and target categories inside one
    ``BEGIN IMMEDIATE`` transaction.  This prevents a failure while writing
    the target category from committing the source-category deletion.
    """

    source_category = str(original_category or "").strip()
    destination_category = str(target_category or source_category).strip()
    clean_item_id = str(item_id or "").strip()
    if (
        source_category not in _memory_api.KNOWLEDGE_CATEGORIES
        or destination_category not in _memory_api.KNOWLEDGE_CATEGORIES
        or not clean_item_id
    ):
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    snapshots: dict[str, list[dict]] = {}
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        source_items = _memory_api.load_knowledge_category_rows(conn, source_category)
        original = next(
            (
                item
                for item in source_items
                if str(item.get("id") or item.get("knowledge_id") or "").strip() == clean_item_id
            ),
            None,
        )
        if original is None:
            conn.rollback()
            return False

        if delete_only:
            deleted, source_after = _memory_api.delete_knowledge_category_item(
                conn,
                source_category,
                clean_item_id,
            )
            if not deleted:
                conn.rollback()
                return False
            snapshots[source_category] = source_after
        else:
            updates = updated_item if isinstance(updated_item, dict) else {}
            normalized = {
                **original,
                **updates,
                "id": clean_item_id,
                "knowledge_id": clean_item_id,
                "category": destination_category,
                "status": str(updates.get("status") or original.get("status") or "confirmed"),
            }
            if destination_category == source_category:
                _, source_after = _memory_api.upsert_knowledge_category_item(
                    conn,
                    source_category,
                    normalized,
                )
                snapshots[source_category] = source_after
            else:
                deleted, source_after = _memory_api.delete_knowledge_category_item(
                    conn,
                    source_category,
                    clean_item_id,
                )
                if not deleted:
                    conn.rollback()
                    return False
                _, target_after = _memory_api.upsert_knowledge_category_item(
                    conn,
                    destination_category,
                    normalized,
                )
                snapshots[source_category] = source_after
                snapshots[destination_category] = target_after
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return True


def merge_confirmed_knowledge_item_records(
    project_name: str,
    category: str,
    item_ids: list[str],
    merged_item: dict,
) -> bool:
    """Atomically replace confirmed knowledge items with one merged item."""

    clean_category = str(category or "").strip()
    clean_item_ids = list(dict.fromkeys(
        str(item_id or "").strip()
        for item_id in item_ids
        if str(item_id or "").strip()
    ))
    if clean_category not in _memory_api.KNOWLEDGE_CATEGORIES or len(clean_item_ids) < 2:
        return False
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _memory_api.load_knowledge_category_rows(conn, clean_category)
        current_by_id = {
            str(item.get("id") or item.get("knowledge_id") or "").strip(): item
            for item in current
        }
        if any(item_id not in current_by_id for item_id in clean_item_ids):
            conn.rollback()
            return False

        normalized = dict(merged_item or {})
        merged_id = str(
            normalized.get("id")
            or normalized.get("knowledge_id")
            or clean_item_ids[0]
        ).strip()
        if not merged_id or (merged_id in current_by_id and merged_id not in clean_item_ids):
            conn.rollback()
            return False
        normalized.update({
            "id": merged_id,
            "knowledge_id": merged_id,
            "category": clean_category,
            "status": str(normalized.get("status") or "confirmed"),
        })
        normalized.setdefault("created_at", current_by_id[clean_item_ids[0]].get("created_at"))

        category_after = current
        for selected_id in clean_item_ids:
            deleted, category_after = _memory_api.delete_knowledge_category_item(
                conn,
                clean_category,
                selected_id,
            )
            if not deleted:
                conn.rollback()
                return False
        _, category_after = _memory_api.upsert_knowledge_category_item(
            conn,
            clean_category,
            normalized,
        )
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return True


def delete_confirmed_knowledge_item_records(
    project_name: str,
    category: str,
    item_ids: list[str],
) -> int:
    """Atomically delete explicitly identified confirmed knowledge items."""

    clean_category = str(category or "").strip()
    clean_item_ids = list(dict.fromkeys(
        str(item_id or "").strip()
        for item_id in item_ids
        if str(item_id or "").strip()
    ))
    if clean_category not in _memory_api.KNOWLEDGE_CATEGORIES or not clean_item_ids:
        return 0
    if _memory_api._project_db_marked_unavailable(project_name):
        raise RuntimeError(f"Project database is unavailable for {project_name}.")

    deleted_count = 0
    category_after: list[dict] = []
    with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _memory_api.load_knowledge_category_rows(conn, clean_category)
        active_ids = {
            str(item.get("id") or item.get("knowledge_id") or "").strip()
            for item in current
        }
        selected_ids = [item_id for item_id in clean_item_ids if item_id in active_ids]
        if not selected_ids:
            conn.rollback()
            return 0
        category_after = current
        for selected_id in selected_ids:
            deleted, category_after = _memory_api.delete_knowledge_category_item(
                conn,
                clean_category,
                selected_id,
            )
            if deleted:
                deleted_count += 1
        conn.commit()

    _memory_api._refresh_knowledge_retrieval_best_effort(project_name)
    return deleted_count


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


def save_analysis_report(project_name: str, analysis_type: str, chapter_no: int, content: str, story_id: str = "default"):
    analysis_type = _memory_api.normalize_storage_component(analysis_type, "Analysis type")
    path = _memory_api._story_path_from_project_path(project_name, story_id, "analysis")
    path.mkdir(parents=True, exist_ok=True)
    file = path / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="analysis_markdown",
        logical_key=f"{analysis_type}_chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"{analysis_type} Chapter {chapter_no:03d} Analysis",
        mime_type="text/markdown",
        metadata={"analysis_type": analysis_type, "chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_analysis_report(project_name: str, analysis_type: str, chapter_no: int, story_id: str = "default") -> str:
    analysis_type = _memory_api.normalize_storage_component(analysis_type, "Analysis type")
    file = _memory_api._story_path_from_project_path(project_name, story_id, "analysis") / f"{analysis_type}_chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def source_package_report_path(project_name: str) -> _memory_api.Path:
    path = _memory_api.project_path(project_name) / "analysis"
    path.mkdir(exist_ok=True)
    return path / "source_package.md"


def save_source_package_report(project_name: str, content: str):
    file = source_package_report_path(project_name)
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="source_package_report",
        logical_key="source_package",
        title="Source Package Report",
        mime_type="text/markdown",
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_source_package_report(project_name: str) -> str:
    file = source_package_report_path(project_name)
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def evaluation_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "evaluation")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_evaluation_report(project_name: str, chapter_no: int, content: str, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    file.write_text(content, encoding="utf-8")
    _memory_api._register_asset_file_best_effort(
        project_name,
        file,
        asset_type="evaluation_markdown",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Evaluation",
        mime_type="text/markdown",
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def save_evaluation_json(project_name: str, chapter_no: int, data: dict, story_id: str = "default"):
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    payload = data if isinstance(data, dict) else {}
    _memory_api._write_json_mirror(file, payload)
    _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="evaluation_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
        title=f"Chapter {chapter_no:03d} Evaluation JSON",
        mime_type="application/json",
        payload=payload,
        metadata={"chapter_no": chapter_no},
    )
    _memory_api.sync_project_retrieval_assets(project_name)


def load_evaluation_report(project_name: str, chapter_no: int, story_id: str = "default") -> str:
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.md"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def load_evaluation_json(project_name: str, chapter_no: int, story_id: str = "default") -> dict | None:
    db_payload = _memory_api._load_asset_payload_from_db_best_effort(
        project_name,
        asset_type="evaluation_json",
        logical_key=f"chapter_{chapter_no:03d}",
        story_id=story_id,
    )
    if isinstance(db_payload, dict):
        return db_payload
    file = evaluation_path(project_name, story_id) / f"chapter_{chapter_no:03d}.json"
    if not file.exists():
        return None
    try:
        payload = _memory_api.json.loads(file.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        _memory_api._sync_asset_payload_to_db_best_effort(
            project_name,
            file,
            asset_type="evaluation_json",
            logical_key=f"chapter_{chapter_no:03d}",
            story_id=story_id,
            title=f"Chapter {chapter_no:03d} Evaluation JSON",
            payload=payload,
            metadata={"chapter_no": chapter_no},
        )
        return payload
    except Exception:
        return None


def runs_path(project_name: str, story_id: str = "default") -> _memory_api.Path:
    path = _memory_api._story_path_from_project_path(project_name, story_id, "runs")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_pipeline_run(project_name: str, run_id: str, content: str, story_id: str = "default"):
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    _memory_api._write_text_mirror(file, content)
    try:
        payload = _memory_api.json.loads(content)
    except Exception:
        payload = None
    artifact_asset_id = _memory_api._sync_asset_payload_to_db_best_effort(
        project_name,
        file,
        asset_type="workflow_run_snapshot",
        logical_key=str(run_id),
        story_id=story_id,
        title=f"Workflow Run {run_id}",
        mime_type="application/json",
        payload=payload if isinstance(payload, dict) else {"raw": content},
        metadata={"run_id": str(run_id)},
    )
    if isinstance(payload, dict):
        if not artifact_asset_id:
            asset_id_source = f"{story_id or 'project'}:workflow_run_snapshot:{run_id}"
            artifact_asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
        _memory_api._sync_workflow_to_db_best_effort(
            project_name,
            lambda conn: _memory_api.sync_workflow_run_snapshot(
                conn,
                run_id=str(run_id),
                payload=payload,
                story_id=story_id,
                artifact_asset_id=artifact_asset_id,
            ),
        )


def load_pipeline_run(project_name: str, run_id: str, story_id: str = "default") -> str:
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    db_payload = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.load_workflow_run_snapshot(conn, run_id, story_id),
        "workflow run snapshot",
    )
    if db_payload is not None:
        if not db_payload:
            return ""
        return _memory_api.json.dumps(db_payload, ensure_ascii=False, indent=2)
    file = runs_path(project_name, story_id) / f"{run_id}.json"
    if not file.exists():
        return ""
    return file.read_text(encoding="utf-8")


def _list_pipeline_runs_from_files(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[str]:
    path = runs_path(project_name, story_id)
    files = sorted(path.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if chapter_no is None:
        return [file.stem for file in files]
    chapter_prefix = f"chapter_{chapter_no:03d}_"
    return [file.stem for file in files if file.stem.startswith(chapter_prefix)]


def list_pipeline_runs(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[str]:
    db_run_ids = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.list_workflow_run_ids(conn, story_id=story_id, chapter_no=chapter_no),
        "workflow run list",
    )
    if db_run_ids is not None:
        return db_run_ids
    run_ids = _list_pipeline_runs_from_files(project_name, chapter_no=chapter_no, story_id=story_id)
    if db_run_ids == [] and run_ids:
        for run_id in run_ids:
            raw = (runs_path(project_name, story_id) / f"{run_id}.json").read_text(encoding="utf-8")
            try:
                payload = _memory_api.json.loads(raw)
            except Exception:
                payload = None
            if not isinstance(payload, dict):
                continue
            asset_id_source = f"{story_id or 'project'}:workflow_run_snapshot:{run_id}"
            artifact_asset_id = "asset_" + _memory_api.hashlib.sha256(asset_id_source.encode("utf-8")).hexdigest()[:24]
            _memory_api._sync_workflow_to_db_best_effort(
                project_name,
                lambda conn, payload=payload, run_id=run_id, artifact_asset_id=artifact_asset_id: _memory_api.sync_workflow_run_snapshot(
                    conn,
                    run_id=str(run_id),
                    payload=payload,
                    story_id=story_id,
                    artifact_asset_id=artifact_asset_id,
                ),
            )
    return run_ids


def list_pipeline_run_summaries(project_name: str, chapter_no: int | None = None, story_id: str = "default") -> list[dict]:
    db_runs = _memory_api._load_runtime_from_db_best_effort(
        project_name,
        lambda conn: _memory_api.list_workflow_run_summaries(conn, story_id=story_id, chapter_no=chapter_no),
        "workflow run summary list",
    )
    if db_runs is not None:
        return db_runs
    summaries: list[dict] = []
    for run_id in _list_pipeline_runs_from_files(project_name, chapter_no=chapter_no, story_id=story_id):
        file = runs_path(project_name, story_id) / f"{run_id}.json"
        payload: dict = {}
        try:
            raw = file.read_text(encoding="utf-8")
            parsed = _memory_api.json.loads(raw)
            payload = parsed if isinstance(parsed, dict) else {}
        except Exception:
            payload = {}
        try:
            payload_chapter_no = int(payload.get("chapter_no"))
        except (TypeError, ValueError):
            match = _memory_api.re.search(r"chapter_(\d+)_", run_id)
            payload_chapter_no = int(match.group(1)) if match else None
        summaries.append({
            "run_id": run_id,
            "story_id": story_id,
            "workflow_type": payload.get("workflow_type", "chapter_pipeline"),
            "status": payload.get("status") or ("completed" if payload.get("success") is True else "unknown"),
            "chapter_no": payload_chapter_no,
            "updated_at": _memory_api.datetime.fromtimestamp(file.stat().st_mtime).isoformat(timespec="seconds") if file.exists() else "",
            "started_at": payload.get("started_at", ""),
            "finished_at": payload.get("finished_at", ""),
            "payload": payload,
        })
    return summaries


def delete_pipeline_run_record(project_name: str, run_id: str, story_id: str = "default") -> bool:
    run_id = _memory_api.normalize_storage_component(run_id, "Workflow run ID")
    if _memory_api._project_db_marked_unavailable(project_name):
        return False
    try:
        with _memory_api.open_project_db(_memory_api.project_path(project_name).resolve()) as conn:
            deleted = _memory_api.delete_workflow_run_snapshot(conn, run_id=run_id, story_id=story_id)
            conn.commit()
            return bool(deleted)
    except Exception as exc:
        _memory_api._DB_UNAVAILABLE_PROJECTS.add(project_name)
        _memory_api.logging.getLogger("novelforge.storage").warning(
            "Failed to delete workflow run from project database for %s/%s: %s",
            project_name,
            run_id,
            exc,
        )
        _memory_api._raise_if_db_only(f"Failed to delete workflow run from project database for {project_name}/{run_id}.", exc)
        return False
