from __future__ import annotations

import re
import shutil
import os
import stat
from datetime import datetime
from pathlib import Path

from memory import (
    BASE_DIR,
    list_arcs,
    list_volumes,
    load_chapter_outline_metadata,
    load_evaluation_json,
    load_evaluation_report,
    load_knowledge_base,
    list_long_reference_batches,
    load_outline,
    load_pending_knowledge_items,
    load_review,
    load_review_json,
    load_source_package_report,
    normalize_project_name,
    project_dir,
    retrieval_sources_path,
    runs_path,
    story_path,
    save_analysis_report,
    save_evaluation_json,
    save_evaluation_report,
    save_review,
    save_review_json,
    sync_project_retrieval_assets,
)


CHAPTER_FILE_PATTERN = re.compile(r"chapter_(\d+)\.md$")
REVIEW_JSON_PATTERN = re.compile(r"chapter_(\d+)\.json$")
ANALYSIS_PATTERN = re.compile(r"(.+)_chapter_(\d+)\.md$")
SOURCE_PACKAGE_REPORT_NAME = "source_package.md"
EVALUATION_PATTERN = re.compile(r"chapter_(\d+)\.md$")


def _project_dir(project_name: str) -> Path:
    target = project_dir(project_name)
    base = BASE_DIR.resolve()
    resolved = target.resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError("Invalid project path.")
    return target


def _story_dir(project_name: str, story_id: str = "default") -> Path:
    return story_path(project_name, story_id)


def _safe_unlink(path: Path) -> bool:
    if not path.exists() or not path.is_file():
        return False
    path.unlink()
    return True


def _timestamp_or_empty(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def _latest_mtime(paths: list[Path]) -> float | None:
    values = [item.stat().st_mtime for item in paths if item.exists()]
    return max(values) if values else None


def delete_project(project_name: str) -> bool:
    target = _project_dir(project_name)
    if not target.exists() or not target.is_dir():
        return False

    def _handle_remove_readonly(func, path, exc_info):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except Exception:
            raise exc_info[1]

    shutil.rmtree(target, onerror=_handle_remove_readonly)
    return True


def rename_project(old_name: str, new_name: str) -> str:
    source = _project_dir(old_name)
    normalized_name = normalize_project_name(new_name)
    target = _project_dir(normalized_name)
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError("Source project does not exist.")
    if target.exists():
        raise FileExistsError("Target project already exists.")
    source.rename(target)
    return normalized_name


def delete_outline(project_name: str, story_id: str = "default") -> bool:
    deleted = _safe_unlink(_story_dir(project_name, story_id) / "outline.md")
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_chapter_outline(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    deleted = _safe_unlink(_story_dir(project_name, story_id) / "chapter_outlines" / f"chapter_{chapter_no:03d}.md")
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_chapter_content(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    deleted = _safe_unlink(_story_dir(project_name, story_id) / "chapters" / f"chapter_{chapter_no:03d}.md")
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_chapter_review(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    review_dir = _story_dir(project_name, story_id) / "reviews"
    deleted_md = _safe_unlink(review_dir / f"chapter_{chapter_no:03d}.md")
    deleted_json = _safe_unlink(review_dir / f"chapter_{chapter_no:03d}.json")
    deleted = deleted_md or deleted_json
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_analysis_report(project_name: str, analysis_type: str, chapter_no: int, story_id: str = "default") -> bool:
    file_name = SOURCE_PACKAGE_REPORT_NAME if analysis_type == "source_package" and chapter_no <= 0 else f"{analysis_type}_chapter_{chapter_no:03d}.md"
    base = _project_dir(project_name) if analysis_type == "source_package" and chapter_no <= 0 else _story_dir(project_name, story_id)
    deleted = _safe_unlink(base / "analysis" / file_name)
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_evaluation_report(project_name: str, chapter_no: int, story_id: str = "default") -> bool:
    evaluation_dir = _story_dir(project_name, story_id) / "evaluation"
    deleted_md = _safe_unlink(evaluation_dir / f"chapter_{chapter_no:03d}.md")
    deleted_json = _safe_unlink(evaluation_dir / f"chapter_{chapter_no:03d}.json")
    deleted = deleted_md or deleted_json
    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_chapter_analysis_bundle(project_name: str, chapter_no: int, story_id: str = "default") -> int:
    analysis_dir = _story_dir(project_name, story_id) / "analysis"
    if not analysis_dir.exists():
        return 0

    deleted = 0
    for file in analysis_dir.glob(f"*_chapter_{chapter_no:03d}.md"):
        if _safe_unlink(file):
            deleted += 1

    if deleted:
        sync_project_retrieval_assets(project_name)
    return deleted


def delete_pipeline_run(project_name: str, run_id: str, story_id: str = "default") -> bool:
    return _safe_unlink(runs_path(project_name, story_id) / f"{run_id}.json")


def save_review_resources(project_name: str, chapter_no: int, markdown: str, json_payload: dict | None = None, story_id: str = "default"):
    save_review(project_name, chapter_no, markdown, story_id=story_id)
    if json_payload is not None:
        save_review_json(project_name, chapter_no, json_payload, story_id=story_id)


def save_analysis_resource(project_name: str, analysis_type: str, chapter_no: int, markdown: str, story_id: str = "default"):
    if analysis_type == "source_package" and chapter_no <= 0:
        from memory import save_source_package_report

        save_source_package_report(project_name, markdown)
    else:
        save_analysis_report(project_name, analysis_type, chapter_no, markdown, story_id=story_id)


def save_evaluation_resource(project_name: str, chapter_no: int, markdown: str, json_payload: dict | None = None, story_id: str = "default"):
    save_evaluation_report(project_name, chapter_no, markdown, story_id=story_id)
    if json_payload is not None:
        save_evaluation_json(project_name, chapter_no, json_payload, story_id=story_id)


def save_retrieval_source_content(project_name: str, relative_path: str, content: str):
    base = retrieval_sources_path(project_name).resolve()
    target = (base / relative_path).resolve()
    if base not in target.parents and target != base:
        raise ValueError("Invalid retrieval source path.")
    if not target.exists() or not target.is_file():
        raise FileNotFoundError("Retrieval source does not exist.")
    target.write_text(content, encoding="utf-8")
    sync_project_retrieval_assets(project_name)


def delete_chapter_runs(project_name: str, chapter_no: int, story_id: str = "default") -> int:
    deleted = 0
    for file in runs_path(project_name, story_id).glob(f"chapter_{chapter_no:03d}_*.json"):
        if _safe_unlink(file):
            deleted += 1
    return deleted


def delete_chapter_bundle(project_name: str, chapter_no: int, *, remove_summary: bool = True, story_id: str = "default") -> dict:
    result = {
        "outline_deleted": delete_chapter_outline(project_name, chapter_no, story_id=story_id),
        "content_deleted": delete_chapter_content(project_name, chapter_no, story_id=story_id),
        "review_deleted": delete_chapter_review(project_name, chapter_no, story_id=story_id),
        "analysis_deleted": delete_chapter_analysis_bundle(project_name, chapter_no, story_id=story_id),
        "evaluation_deleted": delete_evaluation_report(project_name, chapter_no, story_id=story_id),
        "runs_deleted": delete_chapter_runs(project_name, chapter_no, story_id=story_id),
        "summary_deleted": False,
    }

    if remove_summary:
        from memory import load_story_chapter_summaries, save_story_chapter_summaries

        original = load_story_chapter_summaries(project_name, story_id)
        summaries = [
            item for item in original
            if not isinstance(item, dict) or item.get("chapter_no") != chapter_no
        ]
        if summaries != original:
            save_story_chapter_summaries(project_name, story_id, summaries)
            result["summary_deleted"] = True

    sync_project_retrieval_assets(project_name)
    return result


def list_analysis_reports(project_name: str, story_id: str = "default") -> list[dict]:
    analysis_dirs = [_story_dir(project_name, story_id) / "analysis"]
    project_analysis_dir = _project_dir(project_name) / "analysis"
    if project_analysis_dir.exists():
        analysis_dirs.append(project_analysis_dir)
    reports = []
    seen_paths: set[str] = set()
    for analysis_dir in analysis_dirs:
        if not analysis_dir.exists():
            continue
        for file in sorted(analysis_dir.glob("*.md")):
            if str(file) in seen_paths:
                continue
            seen_paths.add(str(file))
            match = ANALYSIS_PATTERN.search(file.name)
            if file.name == SOURCE_PACKAGE_REPORT_NAME:
                analysis_type = "source_package"
                chapter_no = None
            else:
                analysis_type = match.group(1) if match else file.stem
                chapter_no = int(match.group(2)) if match else None
            reports.append({
                "analysis_type": analysis_type,
                "chapter_no": chapter_no,
                "file_name": file.name,
                "updated_at": _timestamp_or_empty(file.stat().st_mtime),
                "path": str(file),
                "preview": load_source_package_report(project_name) if analysis_type == "source_package" else load_text_file(file, fallback=""),
            })
    reports.sort(key=lambda item: (item.get("chapter_no") or 0, item.get("analysis_type", "")))
    return reports


def list_evaluation_reports(project_name: str, story_id: str = "default") -> list[dict]:
    evaluation_dir = _story_dir(project_name, story_id) / "evaluation"
    if not evaluation_dir.exists():
        return []
    reports = []
    for file in sorted(evaluation_dir.glob("chapter_*.md")):
        match = EVALUATION_PATTERN.search(file.name)
        chapter_no = int(match.group(1)) if match else None
        reports.append({
            "chapter_no": chapter_no,
            "file_name": file.name,
            "updated_at": _timestamp_or_empty(file.stat().st_mtime),
            "path": str(file),
        })
    return reports


def list_project_runs(project_name: str, story_id: str = "default") -> list[dict]:
    items = []
    for file in sorted(runs_path(project_name, story_id).glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        chapter_no = None
        match = re.search(r"chapter_(\d+)_", file.stem)
        if match:
            chapter_no = int(match.group(1))
        items.append({
            "run_id": file.stem,
            "chapter_no": chapter_no,
            "updated_at": _timestamp_or_empty(file.stat().st_mtime),
            "path": str(file),
        })
    return items


def list_chapter_inventory(project_name: str, story_id: str = "default") -> list[dict]:
    base = _story_dir(project_name, story_id)
    chapter_numbers: set[int] = set()

    for file in (base / "chapter_outlines").glob("chapter_*.md") if (base / "chapter_outlines").exists() else []:
        match = CHAPTER_FILE_PATTERN.search(file.name)
        if match:
            chapter_numbers.add(int(match.group(1)))

    for file in (base / "chapters").glob("chapter_*.md") if (base / "chapters").exists() else []:
        match = CHAPTER_FILE_PATTERN.search(file.name)
        if match:
            chapter_numbers.add(int(match.group(1)))

    for file in (base / "reviews").glob("chapter_*.md") if (base / "reviews").exists() else []:
        match = CHAPTER_FILE_PATTERN.search(file.name)
        if match:
            chapter_numbers.add(int(match.group(1)))

    for report in list_analysis_reports(project_name, story_id=story_id):
        if isinstance(report.get("chapter_no"), int):
            chapter_numbers.add(int(report["chapter_no"]))

    for report in list_evaluation_reports(project_name, story_id=story_id):
        if isinstance(report.get("chapter_no"), int):
            chapter_numbers.add(int(report["chapter_no"]))

    inventory = []
    for chapter_no in sorted(chapter_numbers):
        outline_file = base / "chapter_outlines" / f"chapter_{chapter_no:03d}.md"
        content_file = base / "chapters" / f"chapter_{chapter_no:03d}.md"
        review_md = base / "reviews" / f"chapter_{chapter_no:03d}.md"
        review_json = base / "reviews" / f"chapter_{chapter_no:03d}.json"
        analysis_reports = [
            report for report in list_analysis_reports(project_name, story_id=story_id)
            if report.get("chapter_no") == chapter_no
        ]
        evaluation_report = load_evaluation_report(project_name, chapter_no, story_id=story_id)
        run_items = [run for run in list_project_runs(project_name, story_id=story_id) if run.get("chapter_no") == chapter_no]

        updated_at = _timestamp_or_empty(_latest_mtime([
            outline_file,
            content_file,
            review_md,
            review_json,
            *[Path(report["path"]) for report in analysis_reports],
            *[Path(run["path"]) for run in run_items],
        ]))

        inventory.append({
            "chapter_no": chapter_no,
            "metadata": load_chapter_outline_metadata(project_name, chapter_no, story_id=story_id),
            "has_outline": outline_file.exists(),
            "has_content": content_file.exists(),
            "has_review_markdown": review_md.exists(),
            "has_review_json": review_json.exists(),
            "analysis_types": sorted({str(report.get("analysis_type", "")) for report in analysis_reports if report.get("analysis_type")}),
            "has_evaluation": bool(evaluation_report.strip() or load_evaluation_json(project_name, chapter_no)),
            "run_count": len(run_items),
            "updated_at": updated_at,
            "outline_preview": load_text_file(outline_file, fallback=""),
            "content_preview": load_text_file(content_file, fallback=""),
            "review_preview": load_review(project_name, chapter_no, story_id=story_id),
            "review_payload": load_review_json(project_name, chapter_no, story_id=story_id) or {},
            "evaluation_preview": evaluation_report,
            "evaluation_payload": load_evaluation_json(project_name, chapter_no, story_id=story_id) or {},
        })
    return inventory


def load_text_file(path: Path, fallback: str = "") -> str:
    if not path.exists() or not path.is_file():
        return fallback
    return path.read_text(encoding="utf-8")


def get_project_summary(project_name: str, story_id: str = "default") -> dict:
    base = _project_dir(project_name)
    from memory import load_story_chapter_summaries
    from setting_knowledge import build_generation_setting_context

    memory = build_generation_setting_context(project_name, story_id)
    knowledge_base = load_knowledge_base(project_name)
    files = [item for item in base.rglob("*") if item.is_file()]
    analysis_reports = list_analysis_reports(project_name, story_id=story_id)
    evaluation_reports = list_evaluation_reports(project_name, story_id=story_id)
    runs = list_project_runs(project_name, story_id=story_id)
    long_reference_batches = list_long_reference_batches(project_name)
    retrieval_files = list(retrieval_sources_path(project_name).rglob("*"))
    retrieval_file_count = len([item for item in retrieval_files if item.is_file()])
    chapter_inventory = list_chapter_inventory(project_name, story_id=story_id)
    volumes = list_volumes(project_name, story_id=story_id)
    arcs = list_arcs(project_name, story_id=story_id)

    return {
        "project_name": project_name,
        "title": memory.get("title", project_name),
        "genre": memory.get("genre", ""),
        "canon_mode": memory.get("canon_mode", ""),
        "chapter_count": len([item for item in chapter_inventory if item.get("has_content")]),
        "chapter_outline_count": len([item for item in chapter_inventory if item.get("has_outline")]),
        "volume_count": len(volumes),
        "arc_count": len(arcs),
        "approved_volume_count": len([item for item in volumes if item.get("has_approved_discussion")]),
        "approved_arc_count": len([item for item in arcs if item.get("has_approved_discussion")]),
        "review_count": len([item for item in chapter_inventory if item.get("has_review_markdown") or item.get("has_review_json")]),
        "analysis_count": len(analysis_reports),
        "evaluation_count": len(evaluation_reports),
        "run_count": len(runs),
        "long_reference_batch_count": len(long_reference_batches),
        "retrieval_source_count": retrieval_file_count,
        "knowledge_item_count": sum(len(items) for items in knowledge_base.values()),
        "pending_knowledge_count": len(load_pending_knowledge_items(project_name)),
        "outline_exists": bool(load_outline(project_name, story_id=story_id).strip()),
        "chapter_summary_count": len(load_story_chapter_summaries(project_name, story_id)),
        "updated_at": _timestamp_or_empty(_latest_mtime(files)),
        "resource_file_count": len(files),
    }


def list_retrieval_sources(project_name: str) -> list[dict]:
    source_root = retrieval_sources_path(project_name)
    items = []
    for file in sorted(source_root.rglob("*")):
        if not file.is_file():
            continue
        items.append({
            "relative_path": file.relative_to(source_root).as_posix(),
            "file_name": file.name,
            "updated_at": _timestamp_or_empty(file.stat().st_mtime),
            "path": str(file),
            "suffix": file.suffix.lower(),
            "preview": load_text_file(file, fallback=""),
        })
    return items
