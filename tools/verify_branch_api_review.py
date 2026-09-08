"""Exercise branch/library HTTP contracts against an isolated real database."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.verify_utils import isolated_workspace


def main() -> int:
    from fastapi.testclient import TestClient
    from novelforge.services import memory
    from novelforge.api.app import create_app

    checks: list[str] = []
    failures: list[str] = []

    def check(value: bool, label: str) -> None:
        (checks if value else failures).append(label)

    old = os.environ.get("NOVELFORGE_DISABLE_BACKGROUND_TASKS")
    os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = "1"
    try:
        with isolated_workspace("novelforge_branch_api_review_"):
            client = TestClient(create_app(), headers={"x-novelforge-client": "vue"}, raise_server_exceptions=False)
            response = client.post("/api/v1/projects", json={"name": "branch-api-review"})
            assert response.status_code == 201, response.text
            project = response.json()["data"]["project"]
            project_name = project["name"]
            base = f"/api/v1/projects/{project['project_id']}"
            initial_reference = client.get(f"{base}/stories/default/legacy-reference-status")
            check(initial_reference.status_code == 200 and initial_reference.json()["data"]["legacy_read_mode"] is False, "new project default story also starts in strict mode")
            response = client.post(f"{base}/stories", json={"name": "Story A", "creation_mode": "conversational"})
            assert response.status_code == 201, response.text
            story = response.json()["data"]["story"]["story_id"]
            path = f"{base}/stories/{story}"
            branch = memory.default_branch_id(story)
            response = client.get(f"{path}/branches")
            check(response.status_code == 200 and any(row["branch_id"] == branch for row in response.json()["data"]["branches"]), "HTTP story exposes default main branch")

            with memory.open_project_db(memory.project_path(project_name).resolve()) as conn:
                conn.execute("UPDATE story_reference_states SET read_mode='legacy', migration_status='pending' WHERE story_id=?", (story,))
                conn.commit()
            response = client.post(f"{path}/branches/{branch}/fork", json={"name": "Unsafe legacy", "allow_current_state": True})
            check(400 <= response.status_code < 500, "legacy story cannot bypass confirmation by creating a current-state variant")
            response = client.post(f"{path}/legacy-reference-migration", json={"selections": [], "confirmed": False})
            check(response.status_code == 400, "empty legacy selection still requires explicit confirmation")
            response = client.post(f"{path}/legacy-reference-migration", json={"selections": [], "confirmed": True})
            check(response.status_code == 200 and response.json()["data"]["state"]["read_mode"] == "strict", "explicit empty selection migrates legacy story atomically")

            response = client.post(f"{path}/branches/{branch}/fork", json={"name": "Child", "allow_current_state": True})
            assert response.status_code == 201, response.text
            result = response.json()["data"]
            child = result["branch"]["branch_id"]
            session = result["session"]["session_id"]
            for endpoint in ("workspace", "structure", "outline", "volumes/1", "arcs/1", "discussions/outline"):
                response = client.get(f"{path}/{endpoint}", params={"branch_id": child})
                check(response.status_code == 409, f"unsupported planning read {endpoint} explicitly rejects a child branch")
            response = client.put(f"{path}/outline", params={"branch_id": branch}, json={"content": "MAIN_OUTLINE_SENTINEL"})
            assert response.status_code == 200, response.text
            response = client.put(f"{path}/outline", params={"branch_id": child}, json={"content": "CHILD_MUST_NOT_OVERWRITE"})
            check(response.status_code == 409, "unsupported child outline mutation is rejected before main write")
            response = client.get(f"{path}/outline", params={"branch_id": branch})
            check(response.status_code == 200 and response.json()["data"]["content"] == "MAIN_OUTLINE_SENTINEL", "rejected child mutation leaves the main outline unchanged")
            response = client.get(f"{path}/structure", params={"branch_id": "foreign_branch"})
            check(400 <= response.status_code < 500, "planning route rejects a foreign or missing branch")
            response = client.get(f"{path}/sessions/{session}", params={"branch_id": branch})
            check(400 <= response.status_code < 500, "session route rejects a conflicting explicit branch")
            response = client.get(f"{path}/sessions/{session}", params={"branch_id": child})
            check(response.status_code == 200, "fork returns a usable session in the selected child")
            response = client.put(f"{path}/profile", params={"branch_id": branch}, json={"profile": {"notes": "API_MAIN_PROFILE"}})
            assert response.status_code == 200, response.text
            response = client.get(f"{path}/profile", params={"branch_id": branch})
            check(response.status_code == 200 and response.json()["data"]["profile"]["notes"] == "API_MAIN_PROFILE", "explicit main-branch profile writes are read back through the same API")
            response = client.put(f"{path}/rules", params={"branch_id": branch}, json={"rules": {"all": ["API_MAIN_RULE"]}})
            assert response.status_code == 200, response.text
            response = client.get(f"{path}/context/preview", params={"branch_id": branch})
            check(response.status_code == 200 and "API_MAIN_RULE" in str(response.json()["data"]), "explicit main-branch rules affect actual generation preview")
            response = client.put(f"{path}/profile", params={"branch_id": child}, json={"profile": {"notes": "API_CHILD_PROFILE"}})
            assert response.status_code == 200, response.text
            response = client.get(f"{path}/profile", params={"branch_id": branch})
            check(response.json()["data"]["profile"]["notes"] == "API_MAIN_PROFILE", "child profile API updates do not change the main profile")

            memory.upsert_knowledge_category_item_record(project_name, "world_rules", {
                "id": "project_rule", "name": "Public source rule", "summary": "PROJECT_RULE",
                "setting_scope": "project", "status": "confirmed", "worldline_id": "main",
                "injection_policy": "always", "setting_role": "core", "setting_field": "world",
            })
            response = client.get(f"{path}/context/preview", params={"query": "PROJECT_RULE"})
            blocks = response.json().get("data", {}).get("blocks", [])
            check(response.status_code == 200 and "PROJECT_RULE" not in "\n".join(str(item.get("content") or "") for item in blocks), "omitted branch preview respects strict story library visibility")
            library = client.post(f"{base}/reference-libraries", json={"title": "Public library"}).json()["data"]["library"]
            lid = library["library_id"]
            release_response = client.post(f"{base}/reference-libraries/{lid}/releases", json={"knowledge_ids": ["project_rule"]})
            assert release_response.status_code == 201, release_response.text
            rid = release_response.json()["data"]["release"]["release_id"]
            with memory.open_project_db(memory.project_path(project_name).resolve()) as conn:
                conn.execute("UPDATE story_reference_states SET read_mode='legacy', migration_status='pending' WHERE story_id=?", (story,))
                conn.commit()
            response = client.post(f"{path}/reference-libraries/{lid}/bindings", json={"release_id": rid})
            check(400 <= response.status_code < 500, "ordinary single-library binding cannot silently migrate a legacy story")
            response = client.post(f"{path}/legacy-reference-migration", json={"selections": [], "confirmed": True})
            assert response.status_code == 200, response.text
            response = client.post(f"{path}/reference-libraries/{lid}/bindings", json={"release_id": rid})
            assert response.status_code in (200, 201), response.text
            binding = response.json()["data"]["binding"]
            check(binding["branch_id"] == branch, "omitted binding branch creates a main-branch private copy")
            response = client.get(f"{path}/reference-context", params={"branch_id": child})
            check(response.status_code == 200 and not response.json()["data"]["visible_knowledge_ids"], "library bound after fork does not appear in the child")

            response = client.patch(f"{path}/branches/{child}", json={"status": "archived"})
            assert response.status_code == 200, response.text
            response = client.post(f"{path}/reference-libraries/{lid}/bindings", json={"release_id": rid, "branch_id": child})
            check(400 <= response.status_code < 500, "archived branch rejects new library bindings")
            response = client.get(f"{path}/reference-context", params={"branch_id": child})
            check(response.status_code == 200, "archived branch reference context remains readable")
            client.close()
    finally:
        if old is None:
            os.environ.pop("NOVELFORGE_DISABLE_BACKGROUND_TASKS", None)
        else:
            os.environ["NOVELFORGE_DISABLE_BACKGROUND_TASKS"] = old
    print(json.dumps({"ok": not failures, "checks": checks, "failures": failures}, ensure_ascii=False, indent=2))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
