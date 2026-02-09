import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


class _BatchOnlyAI:
    model = "mock"

    def __init__(self):
        self.translate_calls = 0
        self.translate_batch_inputs = []

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        self.translate_batch_inputs.append(list(texts))
        # First call: initial translation -> return English to trigger zh fallback.
        if len(self.translate_batch_inputs) == 1:
            return ["O-OR THAT"] * len(texts)
        # Second call: fallback batch -> return Chinese.
        return ["那个大叔"] * len(texts)

    async def translate(self, text):
        self.translate_calls += 1
        return "那个大叔"


class _NoopGoogleTranslator:
    def __init__(self, source=None, target=None):
        self.source = source
        self.target = target

    def translate(self, text):
        return "中文"


def test_translator_zh_fallback_can_use_batched_retranslate(monkeypatch):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")
    monkeypatch.setenv("AI_TRANSLATE_ZH_FALLBACK_BATCH", "1")

    ai = _BatchOnlyAI()
    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: ai)
    translator._translator_class = _NoopGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="O-OR THAT AHJUSSI..?!!?",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "那个大叔"

    # In batch mode the fallback re-translate must not call per-item translate().
    assert ai.translate_calls == 0

    # Expect two translate_batch calls: initial + fallback.
    assert len(ai.translate_batch_inputs) >= 2
    assert ["O-OR THAT"] in ai.translate_batch_inputs

