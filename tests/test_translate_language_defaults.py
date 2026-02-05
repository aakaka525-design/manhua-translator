from fastapi.testclient import TestClient

from app.main import app
from app.deps import get_pipeline, get_settings
from core.models import PipelineResult, TaskContext


class _DummyPipeline:
    def __init__(self):
        self.last_context = None

    async def process(self, context, status_callback=None):
        self.last_context = context
        return PipelineResult(success=True, task=context, processing_time_ms=0, stages_completed=[])


def test_translate_image_uses_settings_defaults(tmp_path):
    img_path = tmp_path / "input.png"
    img_path.write_bytes(b"")

    dummy = _DummyPipeline()

    class _Settings:
        source_language = "ja"
        target_language = "zh-CN"

    def _get_pipeline_override():
        return dummy

    def _get_settings_override():
        return _Settings()

    app.dependency_overrides[get_pipeline] = _get_pipeline_override
    app.dependency_overrides[get_settings] = _get_settings_override

    try:
        client = TestClient(app)
        resp = client.post("/api/v1/translate/image", json={"image_path": str(img_path)})
        assert resp.status_code == 200
        assert dummy.last_context is not None
        assert dummy.last_context.source_language == "ja"
        assert dummy.last_context.target_language == "zh-CN"
    finally:
        app.dependency_overrides = {}
