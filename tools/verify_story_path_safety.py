from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.verify_utils import isolated_workspace

from memory import (
    create_project,
    create_story,
    load_stories_index,
    normalize_story_id,
    save_stories_index,
    set_active_story,
    story_path,
)


def _expect_raises(label: str, failures: list[str], callback) -> None:
    try:
        callback()
    except ValueError:
        return
    failures.append(label)


def _run_verification() -> int:
    project_name = f"_story_path_verify_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    create_project(project_name)
    story = create_story(project_name, "Safe Story")
    story_id = story["story_id"]

    failures: list[str] = []
    root = (Path("data") / "projects" / project_name / "stories").resolve()
    resolved_story_path = story_path(project_name, story_id).resolve()
    if root not in resolved_story_path.parents:
        failures.append("safe_story_path_outside_root")

    invalid_ids = ["", ".", "..", "../escape", "..\\escape", "safe/../escape", "C:escape"]
    for invalid_id in invalid_ids:
        _expect_raises(
            f"normalize_rejects_{invalid_id or 'empty'}",
            failures,
            lambda value=invalid_id: normalize_story_id(value),
        )
        _expect_raises(
            f"story_path_rejects_{invalid_id or 'empty'}",
            failures,
            lambda value=invalid_id: story_path(project_name, value),
        )

    save_stories_index(
        project_name,
        {
            "stories": [
                {"story_id": "../escape", "name": "Bad"},
                {"story_id": "valid_story", "name": "Valid"},
            ],
            "active_story_id": "../escape",
        },
    )
    index = load_stories_index(project_name)
    story_ids = [item.get("story_id") for item in index.get("stories", [])]
    if "../escape" in story_ids:
        failures.append("invalid_story_id_persisted")
    if "valid_story" not in story_ids:
        failures.append("valid_story_id_missing")
    if index.get("active_story_id") != "valid_story":
        failures.append("active_story_id_not_repaired")

    set_active_story(project_name, "valid_story")
    if load_stories_index(project_name).get("active_story_id") != "valid_story":
        failures.append("set_active_story_valid_failed")

    result = {
        "ok": not failures,
        "project_name": project_name,
        "failures": failures,
        "story_ids": story_ids,
        "active_story_id": index.get("active_story_id"),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def main() -> int:
    with isolated_workspace("novelforge_story_path_safety_"):
        return _run_verification()


if __name__ == "__main__":
    raise SystemExit(main())
