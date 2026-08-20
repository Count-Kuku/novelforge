"""Smoke-test the FastAPI contract against an isolated workspace."""

from __future__ import annotations

from tools.verify_utils import isolated_workspace


def main() -> None:
    from fastapi.testclient import TestClient

    with isolated_workspace("novelforge_api_"):
        from novelforge.api.app import create_app

        with TestClient(create_app()) as lifecycle_client:
            response = lifecycle_client.get("/api/v1/health/ready")
            assert response.status_code == 200 and "dispatchers" in response.json()["data"], response.text
            response = lifecycle_client.get("/")
            assert response.status_code == 200 and "no-cache" in response.headers.get("cache-control", ""), response.headers
            response = lifecycle_client.get("/planned")
            assert response.status_code == 200, response.text
            response = lifecycle_client.get("/api/v1/not-a-route")
            assert response.status_code == 404 and "<!doctype html>" not in response.text.lower(), response.text
        readonly_client = TestClient(create_app())
        response = readonly_client.post("/api/v1/projects", json={"name": "blocked"})
        assert response.status_code == 403, response.text
        client = TestClient(create_app(), headers={"x-novelforge-client": "vue"})
        response = client.get("/api/v1/health/ready")
        assert response.status_code == 200, response.text
        assert response.json()["data"]["schema_version"] == 16
        response = client.get("/api/v1/capabilities")
        assert response.status_code == 200 and "chat" in response.json()["data"]["capabilities"], response.text
        response = client.get("/api/v1/settings/developer")
        assert response.status_code == 200 and response.json()["data"]["enabled"] is False and response.json()["data"]["projections"] == [], response.text
        response = client.get("/api/v1/settings/models")
        assert response.status_code == 200 and isinstance(response.json()["data"]["profiles"], list), response.text
        response = client.get("/api/v1/usage")
        assert response.status_code == 200 and "today" in response.json()["data"] and "month" in response.json()["data"], response.text
        response = client.get("/api/v1/usage/breakdown?dimension=operation")
        assert response.status_code == 200 and response.json()["data"]["dimension"] == "operation", response.text

        response = client.post("/api/v1/projects", json={"name": "api-demo", "title": "API Demo"})
        assert response.status_code == 201, response.text
        project = response.json()["data"]["project"]
        project_id = project["project_id"]

        idem_headers = {"idempotency-key": "smoke-project-create"}
        response = client.post("/api/v1/projects", headers=idem_headers, json={"name": "idem-demo"})
        assert response.status_code == 201, response.text
        response = client.post("/api/v1/projects", headers=idem_headers, json={"name": "idem-demo"})
        assert response.status_code == 201 and response.headers.get("x-idempotency-replayed") == "true", response.text

        response = client.post(
            f"/api/v1/projects/{project_id}/stories",
            json={"name": "即时创作", "creation_mode": "conversational"},
        )
        assert response.status_code == 201, response.text
        story = response.json()["data"]["story"]
        assert story["creation_mode"] == "conversational"

        response = client.get(f"/api/v1/projects/{project_id}/stories")
        assert response.status_code == 200, response.text
        assert any(item["story_id"] == story["story_id"] for item in response.json()["data"]["stories"])

        response = client.patch(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/mode",
            json={"creation_mode": "planned"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["story"]["creation_mode"] == "planned"

        response = client.put(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/outline",
            json={"content": "# API 大纲\n\n第一幕。"},
        )
        assert response.status_code == 200, response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/outline")
        assert response.status_code == 200 and "第一幕" in response.json()["data"]["content"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/knowledge/pending")
        assert response.status_code == 200 and isinstance(response.json()["data"]["items"], list), response.text
        response = client.get(f"/api/v1/projects/{project_id}/sources")
        assert response.status_code == 200 and isinstance(response.json()["data"]["sources"], list), response.text
        response = client.get(f"/api/v1/projects/{project_id}/knowledge/graph?story_id={story['story_id']}")
        assert response.status_code == 200 and "nodes" in response.json()["data"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/knowledge/entities?entity_type=character")
        assert response.status_code == 200 and isinstance(response.json()["data"]["items"], list), response.text
        response = client.get("/api/v1/knowledge/schema/characters")
        assert response.status_code == 200 and response.json()["data"]["schema_version"] == 2, response.text
        response = client.get(f"/api/v1/projects/{project_id}/content?story_id={story['story_id']}")
        assert response.status_code == 200 and "items" in response.json()["data"], response.text
        response = client.post(f"/api/v1/projects/{project_id}/content/delete?story_id={story['story_id']}", json={"resource": {"group": "outline"}, "confirm": False})
        assert response.status_code == 422, response.text
        response = client.get(f"/api/v1/projects/{project_id}/ingestion/workbench")
        assert response.status_code == 200 and "batch_rows" in response.json()["data"], response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/ingestion/batch",
            files=[("files", ("batch-notes.txt", b"batch import smoke", "text/plain"))],
            data={"scope": "project", "use_ocr": "false"},
        )
        assert response.status_code == 202 and response.json()["data"]["accepted_count"] == 1 and response.json()["data"]["ocr_requested"] is False, response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/ingestion/ocr-preview",
            files={"file": ("not-a-pdf.txt", b"preview", "text/plain")},
        )
        assert response.status_code == 422, response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/rules")
        assert response.status_code == 200 and "story" in response.json()["data"], response.text
        response = client.put(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/rules", json={"rules": {"style": ["克制"]}})
        assert response.status_code == 200 and response.json()["data"]["saved"], response.text
        response = client.get(f"/api/v1/settings/rules?project_id={project_id}&story_id={story['story_id']}")
        assert response.status_code == 200 and "global" in response.json()["data"] and "project" in response.json()["data"], response.text
        response = client.put(f"/api/v1/settings/rules/project?project_id={project_id}&story_id={story['story_id']}", json={"rules": {"write": ["保持克制"]}})
        assert response.status_code == 200 and response.json()["data"]["saved"], response.text
        response = client.get(f"/api/v1/settings/prompt-options?layer=story&project_id={project_id}&story_id={story['story_id']}")
        assert response.status_code == 200 and isinstance(response.json()["data"]["options"], list), response.text
        response = client.get(f"/api/v1/settings/auto-configuration?operation=chapter_write&project_id={project_id}&story_id={story['story_id']}")
        assert response.status_code == 200 and "state" in response.json()["data"], response.text
        response = client.post(f"/api/v1/settings/auto-configuration?project_id={project_id}&story_id={story['story_id']}", json={"operation": "chapter_write", "goal": "对白节奏"})
        assert response.status_code == 200 and "settings" in response.json()["data"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/context/preview?query=第一幕&budget=12000")
        assert response.status_code == 200 and "assembly_id" in response.json()["data"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/volumes/1")
        assert response.status_code == 200 and "outline" in response.json()["data"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/discussions/volume?asset_no=1")
        assert response.status_code == 200 and response.json()["data"]["asset_type"] == "volume", response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/arcs/1/chapter-plan")
        assert response.status_code == 200 and isinstance(response.json()["data"], dict), response.text
        response = client.put(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/arcs/1/chapter-plan", json={"plan": {"chapters": [{"chapter_no": 1}]}, "report_markdown": "smoke"})
        assert response.status_code == 200 and response.json()["data"]["saved"], response.text
        response = client.post(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/arcs/1/chapter-plan/validate", json={"plan": {"chapters": [{"chapter_no": 1}]}})
        assert response.status_code == 200 and "valid" in response.json()["data"], response.text

        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/profile")
        assert response.status_code == 200 and "target_length" in response.json()["data"]["profile"], response.text
        response = client.put(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/profile",
            json={"profile": {"target_length": "中篇", "workflow_depth": "验证"}},
        )
        assert response.status_code == 200 and response.json()["data"]["profile"]["target_length"] == "中篇", response.text
        response = client.post(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/copy", json={"name": "即时创作副本"})
        assert response.status_code == 201 and response.json()["data"]["story"]["name"] == "即时创作副本", response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/discussions/profile")
        assert response.status_code == 200 and response.json()["data"]["asset_type"] == "profile", response.text
        response = client.put(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/chapters/1",
            json={"content": "第一章正文", "kind": "content"},
        )
        assert response.status_code == 200, response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/chapters/1")
        assert response.status_code == 200 and response.json()["data"]["content"] == "第一章正文", response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/chapters/1/versions")
        assert response.status_code == 200 and response.json()["data"]["versions"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/discussions/chapter?asset_no=1")
        assert response.status_code == 200 and response.json()["data"]["asset_type"] == "chapter", response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions",
            json={"session_goal": "附件冒烟"},
        )
        assert response.status_code == 201, response.text
        session_id = response.json()["data"]["session"]["session_id"]
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions/{session_id}/attachments",
            json={"text": "一段只在本轮使用的资料", "title": "冒烟资料"},
        )
        assert response.status_code == 201 and response.json()["data"]["attachment"]["title"] == "冒烟资料", response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions/{session_id}/attachments/url",
            json={"url": "x"},
        )
        assert response.status_code == 422, response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions/{session_id}/attachments/file",
            files={"file": ("notes.txt", b"file attachment smoke", "text/plain")},
            data={"scope": "session"},
        )
        assert response.status_code == 201 and response.json()["data"]["attachment"], response.text
        response = client.post(
            f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions/{session_id}/actions/plan",
            json={"request": "查询知识：第一幕"},
        )
        assert response.status_code == 201 and response.json()["data"]["action"]["action_id"], response.text
        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/sessions/{session_id}/actions")
        assert response.status_code == 200 and response.json()["data"]["actions"], response.text

        response = client.get(f"/api/v1/projects/{project_id}/stories/{story['story_id']}/events")
        assert response.status_code == 200, response.text
        assert "event: ready" in response.text and "event: done" in response.text

        response = client.get("/api/v1/operations/demo-stream")
        assert response.status_code == 200, response.text
        assert "operation.started" in response.text and "operation.completed" in response.text
        from novelforge.api.operations import operation_registry

        operation_id = operation_registry.start("smoke")
        operation_registry.publish(operation_id, "delta", {"text": "replay"})
        response = client.get(f"/api/v1/operations/{operation_id}/events?after=0")
        assert response.status_code == 200 and response.json()["data"]["events"][0]["event"] == "delta", response.text
        response = client.post(f"/api/v1/operations/{operation_id}/cancel")
        assert response.status_code == 200 and response.json()["data"]["status"] == "cancel_requested", response.text

    print("api smoke verification: ok")


if __name__ == "__main__":
    main()
