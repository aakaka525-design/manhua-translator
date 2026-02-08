from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.deps import get_pipeline, get_settings
from app.main import app
from core.models import PipelineResult, TaskContext, TaskStatus


class _OcrNoTextPipeline:
    async def process(self, context: TaskContext, status_callback=None):
        context.update_status(TaskStatus.FAILED, error="OCR found no text")
        object.__setattr__(context, "error_code", "ocr_no_text")
        return PipelineResult(
            success=False,
            task=context,
            processing_time_ms=1,
            stages_completed=["ocr"],
        )


def _override_settings(data_dir: Path, output_dir: Path):
    return SimpleNamespace(
        source_language="korean",
        target_language="zh",
        data_dir=str(data_dir),
        output_dir=str(output_dir),
    )


def test_translate_image_returns_422_for_ocr_no_text(tmp_path: Path):
    img_path = tmp_path / "input.png"
    img_path.write_bytes(b"img")

    app.dependency_overrides[get_pipeline] = lambda: _OcrNoTextPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(tmp_path, tmp_path / "out")
    try:
        client = TestClient(app)
        resp = client.post("/api/v1/translate/image", json={"image_path": str(img_path)})
        assert resp.status_code == 422
        payload = resp.json()
        assert payload["detail"]["code"] == "ocr_no_text"
    finally:
        app.dependency_overrides = {}


def test_retranslate_page_returns_422_for_ocr_no_text(tmp_path: Path):
    data_dir = tmp_path / "data"
    page = data_dir / "demo" / "chapter-1" / "1.jpg"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(b"img")

    app.dependency_overrides[get_pipeline] = lambda: _OcrNoTextPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, tmp_path / "output")
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/translate/page",
            json={
                "manga_id": "demo",
                "chapter_id": "chapter-1",
                "image_name": "1.jpg",
            },
        )
        assert resp.status_code == 422
        payload = resp.json()
        assert payload["detail"]["code"] == "ocr_no_text"
    finally:
        app.dependency_overrides = {}
