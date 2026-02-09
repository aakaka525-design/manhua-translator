import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


class _SalvageAI:
    model = "mock"

    def __init__(self):
        self.translate_batch_inputs = []

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        # Track calls to prove salvage was triggered.
        self.translate_batch_inputs.append(list(texts))

        # 1) Initial translation: return English to force zh fallback (avoid short-token skip).
        if len(self.translate_batch_inputs) == 1:
            return ["Kim Jihwan"] * len(texts)

        # 2) Batched zh fallback: simulate overload/fallback exhaustion for this item.
        if len(self.translate_batch_inputs) == 2:
            return ["[翻译失败]"] * len(texts)

        # 3) Per-item salvage retry: succeed.
        return ["金志焕"] * len(texts)

    async def translate(self, text):
        # Should not be used in this scenario (we salvage via translate_batch([item])).
        return "[翻译失败]"


class _BadGoogleTranslator:
    def __init__(self, source=None, target=None):
        self.source = source
        self.target = target

    def translate(self, text):
        # If Google fallback were used, we'd still end up with non-CJK output.
        return "BAD"


def test_translator_salvages_failure_marker_after_batched_fallback(monkeypatch):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")
    monkeypatch.setenv("AI_TRANSLATE_ZH_FALLBACK_BATCH", "1")
    monkeypatch.setenv("AI_TRANSLATE_ZH_FALLBACK_SALVAGE", "1")
    monkeypatch.setenv("AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS", "4")

    ai = _SalvageAI()
    translator = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: ai)
    translator._translator_class = _BadGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="korean", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="김지환",
            confidence=0.99,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "金志焕"

    # Initial + batched fallback + per-item salvage retry
    assert len(ai.translate_batch_inputs) == 3
