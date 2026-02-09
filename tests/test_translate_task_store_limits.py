from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.deps import get_pipeline, get_settings
from app.main import app
from app.routes import translate as translate_routes
from core.models import PipelineResult, TaskContext, TaskStatus


class _FastSuccessPipeline:
    async def process(self, context: TaskContext, status_callback=None):
        # Simulate a "real" task object with regions to verify we don't retain them.
        context.update_status(TaskStatus.COMPLETED)
        context.regions = [object(), object()]
        return PipelineResult(
            success=True,
            task=context,
            processing_time_ms=1,
            stages_completed=["ocr", "translator", "inpainter", "renderer"],
        )


def _override_settings(data_dir: Path, output_dir: Path):
    return SimpleNamespace(
        source_language="korean",
        target_language="zh",
        data_dir=str(data_dir),
        output_dir=str(output_dir),
    )


def test_task_store_eviction_and_stripping_for_translate_image(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TRANSLATE_TASK_MAX_STORED", "2")

    img1 = tmp_path / "1.png"
    img2 = tmp_path / "2.png"
    img3 = tmp_path / "3.png"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    img3.write_bytes(b"img")

    # Isolate global state in this test.
    translate_routes._tasks.clear()
    translate_routes._task_meta.clear()

    app.dependency_overrides[get_pipeline] = lambda: _FastSuccessPipeline()
    app.dependency_overrides[get_settings] = lambda: _override_settings(tmp_path, tmp_path / "out")
    try:
        client = TestClient(app)

        r1 = client.post("/api/v1/translate/image", json={"image_path": str(img1)})
        assert r1.status_code == 200
        t1 = r1.json()["task_id"]

        r2 = client.post("/api/v1/translate/image", json={"image_path": str(img2)})
        assert r2.status_code == 200
        t2 = r2.json()["task_id"]

        r3 = client.post("/api/v1/translate/image", json={"image_path": str(img3)})
        assert r3.status_code == 200
        _t3 = r3.json()["task_id"]

        # Oldest task should be evicted (bounded in-memory store).
        status1 = client.get(f"/api/v1/translate/task/{t1}")
        assert status1.status_code == 404

        status2 = client.get(f"/api/v1/translate/task/{t2}")
        assert status2.status_code == 200

        # Task store should not retain large region payloads.
        stored = next(iter(translate_routes._tasks.values()))
        assert stored.regions == []
    finally:
        translate_routes._tasks.clear()
        translate_routes._task_meta.clear()
        app.dependency_overrides = {}

