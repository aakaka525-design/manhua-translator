import asyncio

from PIL import Image

from core.models import TaskContext
from core.modules.ocr import OCRModule
import core.modules.ocr as ocr_module


class _SpyDetector:
    def __init__(self, called):
        self._called = called

    def detect(self, regions, image_shape):
        self._called["value"] = True
        return regions


def _make_image(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (10, 10), color="white").save(path)
    return path


def test_disable_watermark_detector(monkeypatch, tmp_path):
    called = {"value": False}
    monkeypatch.setenv("DISABLE_WATERMARK", "1")
    monkeypatch.setattr(ocr_module, "WatermarkDetector", lambda: _SpyDetector(called))

    module = OCRModule(use_mock=True)
    ctx = TaskContext(image_path=str(_make_image(tmp_path)))
    asyncio.run(module.process(ctx))

    assert called["value"] is False


def test_watermark_detector_runs_by_default(monkeypatch, tmp_path):
    called = {"value": False}
    monkeypatch.delenv("DISABLE_WATERMARK", raising=False)
    monkeypatch.setattr(ocr_module, "WatermarkDetector", lambda: _SpyDetector(called))

    module = OCRModule(use_mock=True)
    ctx = TaskContext(image_path=str(_make_image(tmp_path)))
    asyncio.run(module.process(ctx))

    assert called["value"] is True
