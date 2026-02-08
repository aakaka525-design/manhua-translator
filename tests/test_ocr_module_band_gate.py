from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

import core.modules.ocr as ocr_module
from core.models import Box2D, RegionData, TaskContext
from core.modules.ocr import OCRModule


@pytest.mark.asyncio
async def test_ocr_module_gates_edge_band_ocr(tmp_path: Path, monkeypatch):
    """
    Regression: cross-page edge-band OCR must not overlap with main OCR.

    OCRModule gates detect_and_recognize() via OCR_MAX_CONCURRENCY, but edge-band OCR
    calls (detect_and_recognize_band) must also respect the same gate; otherwise a
    different task can be running main OCR while another task starts band OCR, which
    reproduces PaddleOCR concurrency crashes in production.
    """

    in_main_ocr = {"value": False}
    in_band_ocr = {"value": False}

    class _DummyPaddleOCREngine:
        def __init__(self, lang: str = "en"):
            self.lang = lang

        def _init_ocr(self):
            return self

        async def detect_and_recognize(self, _image_path: str):
            # Any overlap between main OCR and band OCR indicates gate leakage.
            if in_band_ocr["value"]:
                raise RuntimeError("main OCR started while band OCR active")
            if in_main_ocr["value"]:
                raise RuntimeError("main OCR overlapped with main OCR")
            in_main_ocr["value"] = True
            try:
                # Long enough that another task can start band OCR after this task
                # releases the gate, but before this finishes.
                await asyncio.sleep(0.20)
                if in_band_ocr["value"]:
                    raise RuntimeError("main OCR overlapped with band OCR")
                return [
                    RegionData(
                        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                        source_text="hi",
                        confidence=0.9,
                    )
                ]
            finally:
                in_main_ocr["value"] = False

        async def detect_and_recognize_band(
            self, _image_path: str, edge: str, band_height: int
        ):
            if in_main_ocr["value"]:
                raise RuntimeError("band OCR started while main OCR active")
            if in_band_ocr["value"]:
                raise RuntimeError("band OCR overlapped with band OCR")
            in_band_ocr["value"] = True
            try:
                await asyncio.sleep(0.10)
                if in_main_ocr["value"]:
                    raise RuntimeError("band OCR overlapped with main OCR")
            finally:
                in_band_ocr["value"] = False
            # Return at least one region so downstream matching doesn't crash.
            return [
                RegionData(
                    box_2d=Box2D(x1=0, y1=0, x2=10, y2=min(10, band_height)),
                    source_text=f"edge-{edge}",
                    confidence=0.9,
                )
            ]

    monkeypatch.setattr(ocr_module, "PaddleOCREngine", _DummyPaddleOCREngine)
    monkeypatch.setenv("OCR_RESULT_CACHE_ENABLE", "0")
    monkeypatch.setenv("OCR_FAIL_ON_EMPTY", "0")
    monkeypatch.setenv("OCR_CROSSPAGE_EDGE_ENABLE", "1")
    monkeypatch.setenv("OCR_MAX_CONCURRENCY", "1")

    module = OCRModule(lang="en", use_mock=False)

    chapter_dir = tmp_path / "chapter"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    img1 = chapter_dir / "1.png"
    img2 = chapter_dir / "2.png"
    Image.new("RGB", (64, 64), color="white").save(img1)
    Image.new("RGB", (64, 64), color="white").save(img2)

    ctx1 = TaskContext(image_path=str(img1), source_language="korean", target_language="zh-CN")
    ctx2 = TaskContext(image_path=str(img2), source_language="korean", target_language="zh-CN")

    results = await asyncio.gather(
        module.process(ctx1),
        module.process(ctx2),
        return_exceptions=True,
    )

    assert not any(isinstance(r, Exception) for r in results), results
