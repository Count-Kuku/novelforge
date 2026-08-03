from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from novelforge.services.memory import (
    copy_story,
    create_project,
    create_story,
    list_pipeline_run_summaries,
    load_evaluation_json,
    load_outline_discussion_artifact,
    load_pipeline_run,
    load_review_json,
    project_path,
    save_evaluation_json,
    save_outline_discussion_artifact,
    save_pipeline_run,
    save_review_json,
    story_path,
)
from storage import open_project_db
from tools.verify_utils import isolated_workspace


def _expect(condition: bool, label: str, failures: list[str]) -> None:
    if not condition:
        failures.append(label)


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _verify_mode(write_mirrors: bool, failures: list[str]) -> int:
    os.environ["NOVELFORGE_WRITE_JSON_MIRRORS"] = "1" if write_mirrors else "0"
    mode_label = "enabled" if write_mirrors else "disabled"
    project_name = f"story_copy_mirrors_{mode_label}"
    create_project(project_name)
    source_story_id = create_story(project_name, "Source Story")["story_id"]

    source_posix_path = f"stories/{source_story_id}/chapters/chapter_001.md"
    source_windows_path = rf"D:\Novel Forge\stories\{source_story_id}\exports\chapter_001.md"
    prose = f"说明文字引用 stories/{source_story_id}/examples/sample.md，但不是文件字段。"
    workflow_payload = {
        "run_id": "mirror-run",
        "story_id": source_story_id,
        "saved_path": source_posix_path,
        "note": prose,
        "steps": {
            "persist": {
                "status": "completed",
                "output_path": source_windows_path,
                "note": prose,
            }
        },
    }
    review_payload = {
        "story_id": source_story_id,
        "score": 91,
        "saved_path": f"stories/{source_story_id}/reviews/chapter_001.json",
    }
    evaluation_payload = {
        "story_id": source_story_id,
        "score": 88,
        "output_path": rf"stories\{source_story_id}\evaluation\chapter_001.json",
    }
    discussion = {
        "story_id": source_story_id,
        "decision": "keep",
        "saved_path": f"stories/{source_story_id}/outline.discussion.json",
    }
    save_pipeline_run(
        project_name,
        "mirror-run",
        json.dumps(workflow_payload, ensure_ascii=False),
        story_id=source_story_id,
    )
    save_review_json(project_name, 1, review_payload, story_id=source_story_id)
    save_evaluation_json(project_name, 1, evaluation_payload, story_id=source_story_id)
    save_outline_discussion_artifact(
        project_name,
        discussion,
        prose,
        story_id=source_story_id,
    )

    source_dir = story_path(project_name, source_story_id)
    stale_payload = {
        "run_id": "mirror-run",
        "story_id": source_story_id,
        "saved_path": source_posix_path,
        "stale_file": True,
    }
    _write_json(source_dir / "runs" / "mirror-run.json", stale_payload)
    _write_json(source_dir / "runs" / "orphan.json", {"stale_orphan": True})
    _write_json(source_dir / "reviews" / "chapter_001.json", {"stale_review": True})
    _write_json(source_dir / "evaluation" / "chapter_001.json", {"stale_evaluation": True})
    _write_json(source_dir / "outline.discussion.json", {"stale_discussion": True})

    custom_payload = {
        "kind": "user_file",
        "story_id": source_story_id,
        "literal_path": source_posix_path,
    }
    custom_relative_path = Path("user_notes") / "world-map.json"
    _write_json(source_dir / custom_relative_path, custom_payload)

    copied = copy_story(project_name, source_story_id, f"Target {mode_label}")
    target_story_id = copied["story_id"]
    target_dir = story_path(project_name, target_story_id)
    copied_runs = list_pipeline_run_summaries(project_name, story_id=target_story_id)
    _expect(bool(copied_runs), f"{mode_label}:workflow_cloned", failures)
    if not copied_runs:
        return 1
    copied_run_id = str(copied_runs[0]["run_id"])

    target_custom_path = target_dir / custom_relative_path
    _expect(target_custom_path.exists(), f"{mode_label}:custom_json_preserved", failures)
    if target_custom_path.exists():
        _expect(
            json.loads(target_custom_path.read_text(encoding="utf-8")) == custom_payload,
            f"{mode_label}:custom_json_not_rewritten",
            failures,
        )
    _expect(
        not (target_dir / "runs" / "orphan.json").exists(),
        f"{mode_label}:orphan_run_mirror_not_copied",
        failures,
    )

    mirror_paths = [
        target_dir / "creative_profile.json",
        target_dir / "outline.discussion.json",
        target_dir / "reviews" / "chapter_001.json",
        target_dir / "evaluation" / "chapter_001.json",
        target_dir / "runs" / f"{copied_run_id}.json",
    ]
    if not write_mirrors:
        _expect(
            all(not path.exists() for path in mirror_paths),
            "disabled:db_json_mirrors_absent",
            failures,
        )
        copied_json_paths = {
            path.relative_to(target_dir).as_posix()
            for path in target_dir.rglob("*.json")
        }
        _expect(
            copied_json_paths == {custom_relative_path.as_posix()},
            "disabled:only_user_json_is_copied",
            failures,
        )
        return 6

    _expect(all(path.exists() for path in mirror_paths), "enabled:db_json_mirrors_materialized", failures)
    target_posix_path = f"stories/{target_story_id}/chapters/chapter_001.md"
    target_windows_path = rf"D:\Novel Forge\stories\{target_story_id}\exports\chapter_001.md"
    run_file = target_dir / "runs" / f"{copied_run_id}.json"
    run_file_payload = json.loads(run_file.read_text(encoding="utf-8")) if run_file.exists() else {}
    db_run_payload = json.loads(load_pipeline_run(project_name, copied_run_id, story_id=target_story_id))
    _expect(run_file_payload == db_run_payload, "enabled:run_mirror_matches_db", failures)
    _expect(run_file_payload.get("run_id") == copied_run_id, "enabled:run_id_rewritten", failures)
    _expect(run_file_payload.get("story_id") == target_story_id, "enabled:run_story_id_rewritten", failures)
    _expect(run_file_payload.get("saved_path") == target_posix_path, "enabled:run_posix_path_rewritten", failures)
    _expect(
        run_file_payload.get("steps", {}).get("persist", {}).get("output_path") == target_windows_path,
        "enabled:run_windows_path_rewritten",
        failures,
    )
    _expect(run_file_payload.get("note") == prose, "enabled:run_prose_preserved", failures)

    review_file_payload = json.loads(mirror_paths[2].read_text(encoding="utf-8"))
    evaluation_file_payload = json.loads(mirror_paths[3].read_text(encoding="utf-8"))
    discussion_file_payload = json.loads(mirror_paths[1].read_text(encoding="utf-8"))
    _expect(
        review_file_payload == load_review_json(project_name, 1, story_id=target_story_id),
        "enabled:review_mirror_matches_db",
        failures,
    )
    _expect(
        evaluation_file_payload == load_evaluation_json(project_name, 1, story_id=target_story_id),
        "enabled:evaluation_mirror_matches_db",
        failures,
    )
    _expect(
        discussion_file_payload == load_outline_discussion_artifact(project_name, story_id=target_story_id),
        "enabled:discussion_mirror_matches_db",
        failures,
    )
    _expect(
        review_file_payload.get("saved_path") == f"stories/{target_story_id}/reviews/chapter_001.json",
        "enabled:review_path_rewritten",
        failures,
    )
    _expect(
        evaluation_file_payload.get("output_path") == rf"stories\{target_story_id}\evaluation\chapter_001.json",
        "enabled:evaluation_path_rewritten",
        failures,
    )
    _expect(
        discussion_file_payload.get("discussion", {}).get("story_id") == target_story_id,
        "enabled:discussion_story_id_rewritten",
        failures,
    )

    with open_project_db(project_path(project_name).resolve()) as conn:
        hash_row = conn.execute(
            """
            SELECT content_hash
            FROM asset_files
            WHERE story_id = ? AND asset_type = 'workflow_run_snapshot' AND logical_key = ?
            """,
            (target_story_id, copied_run_id),
        ).fetchone()
    expected_hash = hashlib.sha256(run_file.read_bytes()).hexdigest()
    _expect(
        bool(hash_row) and str(hash_row["content_hash"] or "") == expected_hash,
        "enabled:run_mirror_hash_matches_db",
        failures,
    )
    return 18


def main() -> int:
    with isolated_workspace("novelforge_story_copy_mirrors_"):
        failures: list[str] = []
        checks = _verify_mode(False, failures) + _verify_mode(True, failures)
        result = {"ok": not failures, "failures": failures, "checks": checks}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
