import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


class _MockAI:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        return ["한국어"]

    async def translate(self, text):
        return "한국어"


class _MockGoogleTranslator:
    def __init__(self, source=None, target=None):
        self.source = source
        self.target = target

    def translate(self, text):
        return "中文"


class _StrictGoogleTranslator:
    last_target = None

    def __init__(self, source=None, target=None):
        type(self).last_target = target
        if target == "zh":
            raise ValueError("No support for the provided language.")
        self.source = source
        self.target = target

    def translate(self, text):
        return "中文"


def test_translator_retries_when_no_chinese_output(monkeypatch):
    translator = TranslatorModule(source_lang="ko", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockAI())
    translator._translator_class = _MockGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="ko", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="테스트",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "中文"


class _MockFailAI:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        return [f"[翻译失败] {t}" for t in texts]

    async def translate(self, text):
        return f"[翻译失败] {text}"


def test_translator_fallback_when_failure_marker(monkeypatch):
    translator = TranslatorModule(source_lang="en", target_lang="zh", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockFailAI())
    translator._translator_class = _MockGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="WHOA, THEY LOOK GOOD~!",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "中文"


class _MockAIWithCorrection:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        # Return corrected English without CJK characters.
        return ["WHERE'S THE BLANKET!"]

    async def translate(self, text):
        if "BLANKET" in text:
            return "毯子"
        return "错误"


def test_translator_fallback_uses_corrected_translation(monkeypatch):
    translator = TranslatorModule(source_lang="en", target_lang="zh", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockAIWithCorrection())
    translator._translator_class = _MockGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="WHERE'S THE OLAINKEI!",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "毯子"


class _MockMixedAI:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        return ["O-OR THAT 那个大叔..??"]

    async def translate(self, text):
        return "O-OR THAT 那个大叔..??"


class _NoRetryAI:
    model = "mock"
    translate_calls = 0

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        return ["Ina"]

    async def translate(self, text):
        type(self).translate_calls += 1
        return "伊娜"


class _NoRetryGoogleTranslator:
    init_calls = 0

    def __init__(self, source=None, target=None):
        type(self).init_calls += 1
        self.source = source
        self.target = target

    def translate(self, text):
        return "中文"


def test_translator_skips_retranslate_for_short_name_like_token(monkeypatch):
    _NoRetryAI.translate_calls = 0
    _NoRetryGoogleTranslator.init_calls = 0
    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _NoRetryAI())
    translator._translator_class = _NoRetryGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="Ina",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "Ina"
    assert _NoRetryAI.translate_calls == 0
    assert _NoRetryGoogleTranslator.init_calls == 0


def test_translator_fallback_when_english_ratio_high(monkeypatch):
    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockMixedAI())
    translator._translator_class = _MockGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="O-OR THAT AHJUSSI..?!!?",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "中文"


def test_translator_google_fallback_maps_zh_target(monkeypatch):
    translator = TranslatorModule(source_lang="en", target_lang="zh", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockFailAI())
    translator._translator_class = _StrictGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="HELLO",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "中文"
    assert _StrictGoogleTranslator.last_target == "zh-CN"
