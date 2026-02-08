from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.deps import get_pipeline, get_settings
from app.main import app
from app.routes import translate as translate_routes
from core.models import PipelineResult, TaskStatus


class _BatchOcrEmptyPipeline:
    async def process_batch(self, contexts, status_callback=None):
        results = []
        for context in contexts:
            context.update_status(TaskStatus.COMPLETED)
            context.regions = []
            Path(context.output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(context.output_path).write_bytes(b"translated")
            results.append(
                PipelineResult(
                    success=True,
                    task=context,
                    processing_time_ms=1,
                    stages_completed=["ocr", "translator", "inpainter", "renderer"],
                )
            )
        return results


def _override_settings(data_dir: Path, output_dir: Path):
    return SimpleNamespace(
        source_language="korean",
        target_language="zh",
        data_dir=str(data_dir),
        output_dir=str(output_dir),
    )


def test_translate_chapter_excludes_regions_empty_from_success(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    page = data_dir / "demo" / "chapter-1" / "1.jpg"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(b"img")

    events = []

    async def _fake_broadcast(event):
        events.append(event)

    monkeypatch.setattr(translate_routes, "broadcast_event", _fake_broadcast)
    app.dependency_overrides[get_pipeline] = lambda: _BatchOcrEmptyPipeline()
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
        assert completion["failed_ocr_empty_count"] == 1
        assert completion["total_count"] == 1
    finally:
        app.dependency_overrides = {}
