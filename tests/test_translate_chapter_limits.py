from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.deps import get_pipeline, get_settings
from app.main import app
from app.routes import translate as translate_routes
from core.models import PipelineResult, TaskStatus


class _NoopBatchPipeline:
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


class _CaptureBatchConcurrencyPipeline:
    def __init__(self):
        self.max_concurrent = None

    async def process_batch(self, contexts, max_concurrent=5, status_callback=None):
        self.max_concurrent = max_concurrent
        results = []
        for context in contexts:
            context.update_status(TaskStatus.COMPLETED)
            context.regions = [object()]
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


def _create_page(data_dir: Path, manga_id: str, chapter_id: str, image_name: str = "1.jpg"):
    page = data_dir / manga_id / chapter_id / image_name
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_bytes(b"img")


def test_translate_chapter_returns_409_when_same_chapter_already_running(tmp_path: Path):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    manga_id = "demo"
    chapter_id = "chapter-1"
    _create_page(data_dir, manga_id, chapter_id)

    chapter_key = f"{manga_id}/{chapter_id}"
    translate_routes._chapter_jobs_inflight.add(chapter_key)
    app.dependency_overrides[get_pipeline] = lambda: _NoopBatchPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, output_dir)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/translate/chapter",
            json={"manga_id": manga_id, "chapter_id": chapter_id},
        )
        assert resp.status_code == 409
        payload = resp.json()
        assert payload["detail"]["code"] == "chapter_already_running"
    finally:
        translate_routes._chapter_jobs_inflight.discard(chapter_key)
        app.dependency_overrides = {}


def test_translate_chapter_returns_429_when_queue_is_full(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    _create_page(data_dir, "demo", "chapter-1")
    _create_page(data_dir, "other", "chapter-2")

    monkeypatch.setenv("TRANSLATE_CHAPTER_MAX_PENDING_JOBS", "1")
    translate_routes._chapter_jobs_inflight.add("other/chapter-2")
    app.dependency_overrides[get_pipeline] = lambda: _NoopBatchPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, output_dir)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/translate/chapter",
            json={"manga_id": "demo", "chapter_id": "chapter-1"},
        )
        assert resp.status_code == 429
        payload = resp.json()
        assert payload["detail"]["code"] == "chapter_queue_full"
    finally:
        translate_routes._chapter_jobs_inflight.discard("other/chapter-2")
        app.dependency_overrides = {}


def test_translate_chapter_uses_configured_page_concurrency(tmp_path: Path, monkeypatch):
    data_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    _create_page(data_dir, "demo", "chapter-1")

    pipeline = _CaptureBatchConcurrencyPipeline()
    monkeypatch.setenv("TRANSLATE_CHAPTER_PAGE_CONCURRENCY", "2")
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    app.dependency_overrides[get_settings] = lambda: _override_settings(data_dir, output_dir)
    try:
        client = TestClient(app)
        resp = client.post(
            "/api/v1/translate/chapter",
            json={"manga_id": "demo", "chapter_id": "chapter-1"},
        )
        assert resp.status_code == 200
        assert pipeline.max_concurrent == 2
    finally:
        app.dependency_overrides = {}
