import asyncio
import time

from core.crosspage_carryover import CrosspageCarryOverStore
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


class _SleepyAITranslateOK:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        # First pass returns English -> triggers zh fallback retranslate.
        return ["O-OR THAT"] * len(texts)

    async def translate(self, text):
        await asyncio.sleep(0.01)
        return "那个大叔"


class _SleepyAITranslateStillBad:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        # First pass returns English -> triggers zh fallback retranslate.
        return ["O-OR THAT"] * len(texts)

    async def translate(self, text):
        await asyncio.sleep(0.01)
        return "O-OR THAT"


class _SleepyGoogleTranslator:
    def __init__(self, source=None, target=None):
        self.source = source
        self.target = target

    def translate(self, text):
        time.sleep(0.01)
        return "中文"


class _CrosspageAI:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None, **_):
        # 1) For the group translation, return JSON with missing bottom to trigger extra pass.
        if output_format == "json":
            return ['{"top":"上句","bottom":""}' for _ in texts]
        # 2) For crosspage_extra translation (translate_batch([crosspage_extra])) return a real translation.
        await asyncio.sleep(0.01)
        return ["续句" for _ in texts]

    async def translate(self, text):
        return "unused"


def test_translator_metrics_include_zh_retranslate_timer(monkeypatch):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _SleepyAITranslateOK())
    translator._translator_class = _SleepyGoogleTranslator

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

    m = translator.last_metrics or {}
    assert m.get("zh_retranslate_items", 0) >= 1
    assert m.get("zh_retranslate_ms", 0) > 0
    assert m.get("google_fallback_items", 0) == 0
    assert m.get("crosspage_extra_items", 0) == 0
    assert "requests_primary" in m
    assert "requests_fallback" in m
    assert "timeouts_primary" in m
    assert "fallback_provider_calls" in m
    assert "missing_number_retries" in m


def test_translator_metrics_include_google_fallback_timer(monkeypatch):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _SleepyAITranslateStillBad())
    translator._translator_class = _SleepyGoogleTranslator

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

    m = translator.last_metrics or {}
    assert m.get("google_fallback_items", 0) >= 1
    assert m.get("google_fallback_ms", 0) > 0
    assert "requests_primary" in m
    assert "requests_fallback" in m
    assert "timeouts_primary" in m
    assert "fallback_provider_calls" in m
    assert "missing_number_retries" in m


def test_translator_metrics_include_crosspage_extra_timer(monkeypatch, tmp_path):
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    translator = TranslatorModule(source_lang="ko", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _CrosspageAI())
    translator._translator_class = _SleepyGoogleTranslator
    translator._carryover_store = CrosspageCarryOverStore(tmp_path / "carry.jsonl")

    ctx = TaskContext(image_path="/tmp/in.png", source_language="ko", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=50, y2=10),
            source_text="테스트",
            confidence=0.9,
            crosspage_pair_id="pair-1",
            crosspage_role="current_bottom",
            crosspage_texts=["EXTRA"],
        )
    ]

    result = asyncio.run(translator.process(ctx))
    # Crosspage "top" gets assigned to current page.
    assert result.regions[0].target_text == "上句"
    # Extra translation should be stored for next page.
    assert translator._carryover_store.get("pair-1") == "续句"

    m = translator.last_metrics or {}
    assert m.get("crosspage_extra_items", 0) >= 1
    assert m.get("crosspage_extra_ms", 0) > 0
    assert "requests_primary" in m
    assert "requests_fallback" in m
    assert "timeouts_primary" in m
    assert "fallback_provider_calls" in m
    assert "missing_number_retries" in m
