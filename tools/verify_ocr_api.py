"""Verify the OCR preview/batch API contract with a deterministic parser fixture."""

from __future__ import annotations

from unittest.mock import patch

from tools.verify_utils import isolated_workspace


def main() -> None:
    from fastapi.testclient import TestClient

    from novelforge.services.document_parsing import ParsedDocument, ParsedSection

    def fake_ocr(filename: str, data: bytes, *, languages: str = "chi_sim+eng", dpi: int = 200, progress_callback=None) -> ParsedDocument:
        assert filename == "scan.pdf"
        assert data == b"pdf fixture"
        assert languages == "chi_sim+eng"
        assert dpi == 200
        if progress_callback:
            progress_callback({"phase": "ocr", "status": "running", "completed": 0, "total": 1, "percent": 0.0})
            progress_callback({"phase": "ocr", "status": "completed", "completed": 1, "total": 1, "percent": 100.0, "page": 1, "confidence": 88.0})
        return ParsedDocument(
            filename=filename,
            title="scan",
            media_type="application/pdf",
            parser_name="tesseract_ocr",
            sections=[ParsedSection("第 1 页", "fixture text", level=2, location={"page": 1, "ocr_confidence": 88.0})],
            metadata={"page_count": 1, "ocr_page_confidences": [{"page": 1, "confidence": 88.0, "char_count": 12}]},
        )

    with isolated_workspace("novelforge_ocr_api_"):
        from novelforge.api.app import create_app

        client = TestClient(create_app(), headers={"x-novelforge-client": "vue"})
        project_response = client.post("/api/v1/projects", json={"name": "ocr-api"})
        assert project_response.status_code == 201, project_response.text
        project_id = project_response.json()["data"]["project"]["project_id"]
        story_response = client.post(
            f"/api/v1/projects/{project_id}/stories",
            json={"name": "OCR Story", "creation_mode": "planned"},
        )
        assert story_response.status_code == 201, story_response.text
        story_id = story_response.json()["data"]["story"]["story_id"]
        with patch("novelforge.services.document_parsing.ocr_pdf_bytes", side_effect=fake_ocr):
            response = client.post(
                f"/api/v1/projects/{project_id}/stories/{story_id}/ingestion/ocr-preview",
                files={"file": ("scan.pdf", b"pdf fixture", "application/pdf")},
                data={"languages": "chi_sim+eng", "dpi": "200"},
            )
        assert response.status_code == 200, response.text
        payload = response.json()["data"]
        assert payload["parser_name"] == "tesseract_ocr"
        assert payload["sections"][0]["text_preview"] == "fixture text"
        assert payload["progress"][-1]["percent"] == 100.0
        with patch("novelforge.services.document_parsing.ocr_pdf_bytes", side_effect=fake_ocr):
            response = client.post(
                f"/api/v1/projects/{project_id}/stories/{story_id}/ingestion/batch",
                files=[("files", ("scan.pdf", b"pdf fixture", "application/pdf"))],
                data={"scope": "project", "use_ocr": "true"},
            )
        assert response.status_code == 202, response.text
        assert response.json()["data"]["ocr_requested"] is True
        assert response.json()["data"]["accepted_count"] == 1

    print("ocr API verification: ok (preview sections=1, final_percent=100)")


if __name__ == "__main__":
    main()
