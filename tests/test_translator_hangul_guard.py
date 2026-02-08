import asyncio
import re

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_zh_fallback_prefers_source_when_model_output_contains_hangul(monkeypatch):
    """
    Regression (stress evidence):
    Some LLM outputs contain Hangul + English commentary for zh targets. The zh fallback
    should not retranslate that corrupted output; it should fall back to the original
    source text and produce a CJK translation.
    """
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    src = (
        "이수 요건을갖추기위한딸수과정윤리학의 기초과정을 이수하고,다앙한 윤리 사상을 살퍼본 뒤"
    )
    first_out = '다양한 윤리 사상을 살펴본 뒤" (After completing the'

    class _NoopGoogleTranslator:
        def __init__(self, source=None, target=None):
            self.source = source
            self.target = target

        def translate(self, text):
            return text

    class _DummyAI:
        def __init__(self):
            self.model = "dummy"
            self.last_metrics = {"api_calls": 0, "api_calls_fallback": 0}
            self.translate_calls = []

        async def translate_batch(self, texts, **kwargs):
            self.last_metrics = {"api_calls": 1, "api_calls_fallback": 0}
            return [first_out for _ in texts]

        async def translate(self, text):
            self.translate_calls.append(text)
            self.last_metrics = {"api_calls": 1, "api_calls_fallback": 0}
            if text == src:
                return "在修满伦理学基础课程并考察多种伦理思想之后"
            return text

    dummy = _DummyAI()
    module = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    module._translator_class = _NoopGoogleTranslator  # prevent deep_translator import
    module._get_ai_translator = lambda: dummy

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=src,
    )
    ctx = TaskContext(
        image_path="/tmp/hangul_guard.png",
        source_language="korean",
        target_language="zh-CN",
        regions=[region],
    )

    asyncio.run(module.process(ctx))

    out = (ctx.regions[0].target_text or "").strip()
    assert re.search(r"[\u4e00-\u9fff]", out)
    assert not re.search(r"[\uac00-\ud7a3\u3130-\u318f\u1100-\u11ff]", out)
    assert dummy.translate_calls and dummy.translate_calls[0] == src


def test_unknown_hangul_sfx_is_kept_original_without_render_or_inpaint(monkeypatch):
    """
    Regression (stress evidence):
    When a Hangul SFX token is not in the SFX dictionary, translate_sfx() returns the
    original Hangul. Rendering that creates unreadable output for zh readers.

    For unknown Hangul SFX, keep original art by leaving target_text empty.
    """
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="스스",
    )
    ctx = TaskContext(
        image_path="/tmp/sfx.png",
        source_language="korean",
        target_language="zh-CN",
        regions=[region],
    )

    module = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    asyncio.run(module.process(ctx))

    assert (ctx.regions[0].target_text or "") == ""

