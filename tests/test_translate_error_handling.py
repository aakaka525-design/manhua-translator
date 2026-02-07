from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.deps import get_pipeline, get_settings
from app.main import app
from app.routes import translate as translate_routes
from core.models import PipelineResult, TaskStatus


class _FailingPipeline:
    async def process(self, context, status_callback=None):
        context.update_status(TaskStatus.FAILED, error="mock pipeline failure")
        return PipelineResult(
            success=False,
            task=context,
            processing_time_ms=0,
            stages_completed=["ocr"],
        )


class _FailingBatchPipeline:
    async def process_batch(self, contexts, status_callback=None):
        results = []
        for context in contexts:
            context.update_status(TaskStatus.FAILED, error="mock batch failure")
            results.append(
                PipelineResult(
                    success=False,
                    task=context,
                    processing_time_ms=0,
                    stages_completed=["ocr"],
                )
            )
        return results


def _override_settings(data_dir: Path, output_dir: Path):
    return SimpleNamespace(
        source_language="ja",
        target_language="zh-CN",
        data_dir=str(data_dir),
        output_dir=str(output_dir),
    )


def test_translate_image_returns_http_500_on_pipeline_failure(tmp_path):
    img_path = tmp_path / "input.png"
    img_path.write_bytes(b"img")

    app.dependency_overrides[get_pipeline] = lambda: _FailingPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(tmp_path, tmp_path / "out")
    try:
        client = TestClient(app)
        resp = client.post("/api/v1/translate/image", json={"image_path": str(img_path)})
        assert resp.status_code == 500
        payload = resp.json()
        assert payload["detail"]["message"] == "mock pipeline failure"
        assert payload["detail"]["status"] == "failed"
    finally:
        app.dependency_overrides = {}


def test_retranslate_page_returns_http_500_on_pipeline_failure(tmp_path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    page = data_dir / "demo" / "chapter-1" / "1.jpg"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(b"img")

    app.dependency_overrides[get_pipeline] = lambda: _FailingPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, output_dir)
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
        assert resp.status_code == 500
        payload = resp.json()
        assert payload["detail"]["message"] == "mock pipeline failure"
        assert payload["detail"]["status"] == "failed"
    finally:
        app.dependency_overrides = {}


def test_translate_chapter_emits_error_status_when_batch_fails(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    page = data_dir / "demo" / "chapter-1" / "1.jpg"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(b"img")

    events = []

    async def _fake_broadcast(event):
        events.append(event)

    monkeypatch.setattr(translate_routes, "broadcast_event", _fake_broadcast)
    app.dependency_overrides[get_pipeline] = lambda: _FailingBatchPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, output_dir)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/translate/chapter",
            json={"manga_id": "demo", "chapter_id": "chapter-1"},
        )
        assert resp.status_code == 200

        complete_events = [e for e in events if e.get("type") == "chapter_complete"]
        assert complete_events
        completion = complete_events[-1]
        assert completion["status"] == "error"
        assert completion["success_count"] == 0
        assert completion["failed_count"] == 1
        assert completion["total_count"] == 1
    finally:
        app.dependency_overrides = {}
