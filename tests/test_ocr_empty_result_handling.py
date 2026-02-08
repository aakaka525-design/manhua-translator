from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from core.models import TaskContext, TaskStatus
from core.modules.base import BaseModule
from core.modules.ocr import OCRModule
from core.pipeline import Pipeline


class _NoopModule(BaseModule):
    async def process(self, context: TaskContext) -> TaskContext:
        return context


@pytest.mark.asyncio
async def test_ocr_module_raises_ocr_no_text_when_regions_empty(tmp_path: Path, monkeypatch):
    img_path = tmp_path / "input.png"
    Image.new("RGB", (32, 32), color="white").save(img_path)

    monkeypatch.setenv("OCR_FAIL_ON_EMPTY", "1")
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "0")

    module = OCRModule(use_mock=True)

    async def _empty_detect(_image_path: str):
        return []

    module.engine.detect_and_recognize = _empty_detect  # type: ignore[attr-defined]

    context = TaskContext(
        image_path=str(img_path),
        source_language="korean",
        target_language="zh",
    )

    with pytest.raises(Exception) as exc_info:  # noqa: B017
        await module.process(context)

    assert getattr(exc_info.value, "error_code", None) == "ocr_no_text"


def test_ocr_cache_skips_empty_results_by_default(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "1")
    monkeypatch.setenv("OCR_RESULT_CACHE_DIR", str(tmp_path))
    monkeypatch.delenv("OCR_CACHE_EMPTY_RESULTS", raising=False)

    module = OCRModule(use_mock=True)
    module._save_cached_regions("/tmp/missing.png", "korean", [])

    assert list(tmp_path.glob("*.json")) == []


@pytest.mark.asyncio
async def test_pipeline_marks_failed_with_ocr_no_text(tmp_path: Path, monkeypatch):
    img_path = tmp_path / "input.png"
    Image.new("RGB", (64, 64), color="white").save(img_path)

    monkeypatch.setenv("OCR_FAIL_ON_EMPTY", "1")
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "0")
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path / "reports"))

    ocr = OCRModule(use_mock=True)

    async def _empty_detect(_image_path: str):
        return []

    ocr.engine.detect_and_recognize = _empty_detect  # type: ignore[attr-defined]

    pipeline = Pipeline(
        ocr=ocr,
        translator=_NoopModule("translator"),
        inpainter=_NoopModule("inpainter"),
        renderer=_NoopModule("renderer"),
        upscaler=_NoopModule("upscaler"),
    )
    context = TaskContext(
        image_path=str(img_path),
        source_language="korean",
        target_language="zh",
    )

    result = await pipeline.process(context)

    assert result.success is False
    assert result.task.status == TaskStatus.FAILED
    assert result.task.error_code == "ocr_no_text"

    reports = list((tmp_path / "reports").glob("*.json"))
    assert reports, "quality report should be written for failed task"
    payload = reports[-1].read_text(encoding="utf-8")
    assert "\"success\": false" in payload
    assert "\"error_code\": \"ocr_no_text\"" in payload
