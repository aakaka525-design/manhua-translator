from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

import core.modules.ocr as ocr_module
from core.models import Box2D, RegionData, TaskContext
from core.modules.ocr import OCRModule


@pytest.mark.asyncio
async def test_ocr_module_does_not_switch_engine_during_inference(tmp_path: Path, monkeypatch):
    """
    Regression test: OCRModule switches PaddleOCREngine based on context.source_language.

    That switch must be synchronized with inference; otherwise concurrent requests with
    different languages can corrupt the underlying OCR runtime and crash/hang the API.
    """

    active_lang: dict[str, str] = {"value": "en"}

    class _DummyPaddleOCREngine:
        def __init__(self, lang: str = "en"):
            self.lang = lang

        def _init_ocr(self):
            # Simulate a global runtime config that would be unsafe to change mid-inference.
            active_lang["value"] = self.lang
            return self

        async def detect_and_recognize(self, _image_path: str):
            start_lang = active_lang["value"]
            # Yield control to let another task attempt to switch engines concurrently.
            await asyncio.sleep(0.05)
            if active_lang["value"] != start_lang:
                raise RuntimeError(
                    f"OCR engine switched during inference: {start_lang} -> {active_lang['value']}"
                )
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                    source_text="hi",
                    confidence=0.9,
                )
            ]

    monkeypatch.setattr(ocr_module, "PaddleOCREngine", _DummyPaddleOCREngine)
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "0")
    monkeypatch.setenv("OCR_FAIL_ON_EMPTY", "0")

    module = OCRModule(lang="en", use_mock=False)

    img_a = tmp_path / "a.png"
    img_b = tmp_path / "b.png"
    Image.new("RGB", (32, 32), color="white").save(img_a)
    Image.new("RGB", (32, 32), color="white").save(img_b)

    # Different source languages on the same OCRModule instance should not race.
    ctx_a = TaskContext(
        image_path=str(img_a),
        source_language="korean",
        target_language="zh-CN",
    )
    ctx_b = TaskContext(
        image_path=str(img_b),
        source_language="japanese",
        target_language="zh-CN",
    )

    results = await asyncio.gather(
        module.process(ctx_a),
        module.process(ctx_b),
        return_exceptions=True,
    )

    assert not any(isinstance(r, Exception) for r in results), results

