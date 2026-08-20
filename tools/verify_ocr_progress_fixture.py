"""Run a deterministic page-level OCR fixture without requiring Tesseract locally."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

from novelforge.services import document_parsing


class _Pixmap:
    width = 2
    height = 2
    samples = b"\x00" * 12


class _Page:
    def get_pixmap(self, *, matrix, alpha):  # noqa: ANN001 - fixture protocol
        assert matrix == (200 / 72.0, 200 / 72.0)
        assert alpha is False
        return _Pixmap()


class _Pdf:
    page_count = 3

    def load_page(self, index: int):
        assert 0 <= index < self.page_count
        return _Page()

    def close(self) -> None:
        return None


def main() -> None:
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.Matrix = lambda x, y: (x, y)
    fake_fitz.open = lambda *, stream, filetype: _Pdf()

    fake_tesseract = types.ModuleType("pytesseract")
    fake_tesseract.Output = types.SimpleNamespace(DICT="dict")
    calls = {"count": 0}

    def image_to_data(image, *, lang, output_type):  # noqa: ANN001 - fixture protocol
        assert lang == "chi_sim+eng"
        assert output_type == "dict"
        calls["count"] += 1
        return [
            {"text": ["第一", "页"], "conf": ["95", "90"]},
            {"text": ["低置信度"], "conf": ["50"]},
            {"text": [""], "conf": ["-1"]},
        ][calls["count"] - 1]
    fake_tesseract.image_to_data = image_to_data

    fake_pil = types.ModuleType("PIL")
    fake_image = types.ModuleType("PIL.Image")
    fake_image.frombytes = lambda mode, size, samples: (mode, size, samples)
    fake_pil.Image = fake_image

    progress: list[dict] = []
    with patch.dict(
        sys.modules,
        {"fitz": fake_fitz, "pytesseract": fake_tesseract, "PIL": fake_pil, "PIL.Image": fake_image},
    ):
        with patch.object(
            document_parsing,
            "get_local_ocr_readiness",
            return_value={"available": True, "engine": "tesseract", "version": "fixture"},
        ):
            parsed = document_parsing.ocr_pdf_bytes(
                "fixture-scan.pdf",
                b"%PDF-fixture%",
                progress_callback=progress.append,
            )

    assert parsed.parser_name == "tesseract_ocr"
    assert parsed.metadata["page_count"] == 3
    assert parsed.metadata["empty_page_count"] == 1
    assert parsed.metadata["ocr_engine_version"] == "fixture"
    assert parsed.metadata["ocr_page_confidences"] == [
        {"page": 1, "confidence": 92.5, "char_count": 4},
        {"page": 2, "confidence": 50.0, "char_count": 4},
        {"page": 3, "confidence": 0.0, "char_count": 0},
    ]
    assert [section.text for section in parsed.sections] == ["第一 页", "低置信度"]
    assert any("低于 60" in warning for warning in parsed.warnings)
    assert progress[0] == {
        "phase": "ocr",
        "status": "running",
        "completed": 0,
        "total": 3,
        "percent": 0.0,
    }
    assert progress[-1]["status"] == "completed"
    assert progress[-1]["completed"] == progress[-1]["total"] == 3
    assert progress[-1]["percent"] == 100.0
    assert [item["page"] for item in progress[1:]] == [1, 2, 3]
    print("ocr progress fixture verification: ok (pages=3, final_percent=100)")


if __name__ == "__main__":
    main()
