import pytest

from core.model_setup import ModelRegistry, ModelWarmupService


def test_model_registry_default_state():
    registry = ModelRegistry()
    snapshot = registry.snapshot()
    assert "ppocr_det" in snapshot
    assert snapshot["ppocr_det"]["status"] in {"missing", "ready", "failed"}


@pytest.mark.asyncio
async def test_model_warmup_marks_ready(monkeypatch):
    registry = ModelRegistry()

    async def fake_get_cached_ocr(lang="en"):
        return object()

    def fake_create_inpainter(prefer_lama=True, device="cpu"):
        return object()

    monkeypatch.setattr("core.model_setup.get_cached_ocr", fake_get_cached_ocr)
    monkeypatch.setattr("core.model_setup.create_inpainter", fake_create_inpainter)

    service = ModelWarmupService(registry)
    await service.warmup()

    snapshot = registry.snapshot()
    assert snapshot["ppocr_det"]["status"] == "ready"
    assert snapshot["ppocr_rec"]["status"] == "ready"
    assert snapshot["lama"]["status"] == "ready"
