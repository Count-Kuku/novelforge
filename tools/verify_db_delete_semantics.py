from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "1"

from memory import (
    create_project,
    create_long_reference_batch,
    delete_long_reference_batch,
    delete_retrieval_source_file,
    delete_arc_chapter_plan,
    delete_arc_discussion_artifact,
    delete_chapter_discussion_artifact,
    delete_creative_profile_discussion_artifact,
    delete_outline_discussion_artifact,
    delete_volume_discussion_artifact,
    inspect_project_database,
    load_arc_chapter_plan,
    load_arc_discussion_artifact,
    load_chapter_discussion_artifact,
    load_creative_profile_discussion_artifact,
    load_long_reference_batch,
    load_outline_discussion_artifact,
    load_volume_discussion_artifact,
    list_retrieval_source_files,
    long_reference_batch_path,
    project_path,
    retrieval_sources_path,
    save_arc_chapter_plan,
    save_arc_discussion_artifact,
    save_analysis_report,
    save_chapter,
    save_chapter_outline,
    save_chapter_discussion_artifact,
    save_creative_profile_discussion_artifact,
    save_evaluation_report,
    save_outline_discussion_artifact,
    save_outline,
    save_review,
    save_volume_discussion_artifact,
    sync_retrieval_source_file_record,
)
from project_manager import (
    delete_analysis_report,
    delete_chapter_content,
    delete_chapter_outline,
    delete_chapter_review,
    delete_evaluation_report,
    delete_outline,
    list_analysis_reports,
    list_chapter_inventory,
    list_evaluation_reports,
)


def _project_name_from_args() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        name = sys.argv[1].strip()
        if not name.startswith("_db_delete_verify_"):
            raise SystemExit("Project name must start with _db_delete_verify_ to avoid deleting real files.")
        return name
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"_db_delete_verify_{stamp}"


def _safe_unlink(project_root: Path, file: Path) -> bool:
    resolved_root = project_root.resolve()
    resolved_file = file.resolve()
    if resolved_root != resolved_file and resolved_root not in resolved_file.parents:
        raise RuntimeError(f"Refusing to delete outside verification project: {resolved_file}")
    if not resolved_file.exists() or not resolved_file.is_file():
        return False
    resolved_file.unlink()
    return True


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def main() -> int:
    project_name = _project_name_from_args()
    create_project(project_name)

    save_creative_profile_discussion_artifact(project_name, {"marker": "creative"}, "creative report")
    save_outline_discussion_artifact(project_name, {"marker": "outline"}, "outline report")
    save_volume_discussion_artifact(project_name, 1, {"marker": "volume"}, "volume report")
    save_arc_discussion_artifact(project_name, 1, {"marker": "arc"}, "arc report")
    save_arc_chapter_plan(project_name, 1, {"marker": "plan"}, "plan report")
    save_chapter_discussion_artifact(project_name, 1, {"marker": "chapter"}, "chapter report")
    save_outline(project_name, "outline body")
    save_chapter_outline(project_name, 3, "chapter outline body")
    save_chapter(project_name, 3, "chapter body")
    save_review(project_name, 3, "review markdown")
    save_analysis_report(project_name, "consistency", 3, "analysis markdown")
    save_evaluation_report(project_name, 3, "evaluation markdown")
    batch = create_long_reference_batch(
        project_name,
        title="DB Only Batch",
        scope="reference",
        authority="curated",
        source_type="canon",
        content_fingerprint="db_only_batch",
        segments=[{"title": "DB Only Segment", "content": "batch source text"}],
    )
    source_file = retrieval_sources_path(project_name) / "db_only_source.md"
    source_file.write_text("db only source", encoding="utf-8")
    sync_retrieval_source_file_record(
        project_name,
        relative_path="db_only_source.md",
        title="DB Only Source",
        metadata={"relative_path": "db_only_source.md"},
    )

    root = project_path(project_name)
    mirrors = [
        root / "stories" / "default" / "creative_profile.discussion.json",
        root / "stories" / "default" / "outline.discussion.json",
        root / "stories" / "default" / "volumes" / "volume_001.discussion.json",
        root / "stories" / "default" / "arcs" / "arc_001.discussion.json",
        root / "stories" / "default" / "arcs" / "arc_001.chapter_plan.json",
        root / "stories" / "default" / "chapter_outlines" / "chapter_001.discussion.json",
        root / "stories" / "default" / "outline.md",
        root / "stories" / "default" / "chapter_outlines" / "chapter_003.md",
        root / "stories" / "default" / "chapters" / "chapter_003.md",
        root / "stories" / "default" / "reviews" / "chapter_003.md",
        root / "stories" / "default" / "analysis" / "consistency_chapter_003.md",
        root / "stories" / "default" / "evaluation" / "chapter_003.md",
        long_reference_batch_path(project_name, batch["batch_id"]),
        root / "retrieval" / "sources" / "db_only_source.md",
    ]
    deleted_mirrors = []
    for file in mirrors:
        if _safe_unlink(root, file):
            deleted_mirrors.append(str(file.relative_to(root)))

    failures: list[str] = []
    _expect(load_creative_profile_discussion_artifact(project_name).get("discussion", {}).get("marker") == "creative", "preload_creative", failures)
    _expect(load_outline_discussion_artifact(project_name).get("discussion", {}).get("marker") == "outline", "preload_outline", failures)
    _expect(load_volume_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "volume", "preload_volume", failures)
    _expect(load_arc_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "arc", "preload_arc", failures)
    _expect(load_arc_chapter_plan(project_name, 1).get("plan", {}).get("marker") == "plan", "preload_arc_plan", failures)
    _expect(load_chapter_discussion_artifact(project_name, 1).get("discussion", {}).get("marker") == "chapter", "preload_chapter", failures)
    _expect(load_long_reference_batch(project_name, batch["batch_id"]).get("title") == "DB Only Batch", "preload_long_batch", failures)
    _expect("db_only_source.md" in list_retrieval_source_files(project_name), "preload_retrieval_source", failures)
    inventory = list_chapter_inventory(project_name)
    _expect(any(
        item.get("chapter_no") == 3
        and item.get("has_outline") is True
        and item.get("has_content") is True
        and item.get("has_review_markdown") is True
        and item.get("has_evaluation") is True
        for item in inventory
    ), "preload_long_text_inventory", failures)
    _expect(any(report.get("analysis_type") == "consistency" and report.get("chapter_no") == 3 for report in list_analysis_reports(project_name)), "preload_analysis_asset", failures)
    _expect(any(report.get("chapter_no") == 3 for report in list_evaluation_reports(project_name)), "preload_evaluation_asset", failures)

    _expect(delete_creative_profile_discussion_artifact(project_name) is True, "delete_creative", failures)
    _expect(delete_outline_discussion_artifact(project_name) is True, "delete_outline", failures)
    _expect(delete_volume_discussion_artifact(project_name, 1) is True, "delete_volume", failures)
    _expect(delete_arc_discussion_artifact(project_name, 1) is True, "delete_arc", failures)
    _expect(delete_arc_chapter_plan(project_name, 1) is True, "delete_arc_plan", failures)
    _expect(delete_chapter_discussion_artifact(project_name, 1) is True, "delete_chapter", failures)
    _expect(delete_long_reference_batch(project_name, batch["batch_id"]) is True, "delete_long_batch", failures)
    _expect(delete_retrieval_source_file(project_name, "db_only_source.md") is True, "delete_retrieval_source", failures)
    _expect(delete_outline(project_name) is True, "delete_outline_markdown", failures)
    _expect(delete_chapter_outline(project_name, 3) is True, "delete_chapter_outline_markdown", failures)
    _expect(delete_chapter_content(project_name, 3) is True, "delete_chapter_markdown", failures)
    _expect(delete_chapter_review(project_name, 3) is True, "delete_review_markdown", failures)
    _expect(delete_analysis_report(project_name, "consistency", 3) is True, "delete_analysis_markdown", failures)
    _expect(delete_evaluation_report(project_name, 3) is True, "delete_evaluation_markdown", failures)

    _expect(load_creative_profile_discussion_artifact(project_name) == {}, "postload_creative", failures)
    _expect(load_outline_discussion_artifact(project_name) == {}, "postload_outline", failures)
    _expect(load_volume_discussion_artifact(project_name, 1) == {}, "postload_volume", failures)
    _expect(load_arc_discussion_artifact(project_name, 1) == {}, "postload_arc", failures)
    _expect(load_arc_chapter_plan(project_name, 1) == {}, "postload_arc_plan", failures)
    _expect(load_chapter_discussion_artifact(project_name, 1) == {}, "postload_chapter", failures)
    _expect(load_long_reference_batch(project_name, batch["batch_id"]) == {}, "postload_long_batch", failures)
    _expect("db_only_source.md" not in list_retrieval_source_files(project_name), "postload_retrieval_source", failures)
    post_inventory = list_chapter_inventory(project_name)
    _expect(not any(item.get("chapter_no") == 3 for item in post_inventory), "postload_long_text_inventory", failures)
    _expect(not any(report.get("analysis_type") == "consistency" and report.get("chapter_no") == 3 for report in list_analysis_reports(project_name)), "postload_analysis_asset", failures)
    _expect(not any(report.get("chapter_no") == 3 for report in list_evaluation_reports(project_name)), "postload_evaluation_asset", failures)

    health = inspect_project_database(project_name)
    result = {
        "project_name": project_name,
        "ok": not failures and health.get("ok"),
        "deleted_json_mirrors": deleted_mirrors,
        "failures": failures,
        "health": health,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
