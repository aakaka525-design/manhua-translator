import asyncio
import os

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_uses_post_rec_override(monkeypatch):
    class _FakeEngine:
        def __init__(self, lang="en"):
            self.lang = lang

        def _init_ocr(self):
            return None

    async def _fake_post_rec(image_path, groups, engine, **kwargs):
        return {0: "OVERRIDE"}

    monkeypatch.setenv("POST_REC", "1")
    monkeypatch.setattr("core.modules.translator.PaddleOCREngine", _FakeEngine)
    monkeypatch.setattr(
        "core.modules.translator.post_recognize_groups", _fake_post_rec
    )

    ctx = TaskContext(image_path="/tmp/input.png")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="ORIG",
            confidence=0.9,
        )
    ]

    module = TranslatorModule(source_lang="korean", target_lang="zh", use_mock=True, use_ai=False)
    result = asyncio.run(module.process(ctx))

    assert result.regions[0].target_text == "[翻译] OVERRIDE"
