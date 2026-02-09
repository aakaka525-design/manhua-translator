import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_single_letter_ascii_is_treated_as_ocr_noise(monkeypatch):
    """
    Regression (stress evidence):
    Very short ASCII tokens (e.g. single 'W') can trigger the LLM to hallucinate commentary instead
    of translating. For zh targets, do not keep such output; prefer erase-only behavior.
    """
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    class _DummyAI:
        model = "dummy"
        last_metrics = {"api_calls": 0, "api_calls_fallback": 0}

        async def translate_batch(self, *args, **kwargs):
            self.last_metrics = {"api_calls": 1, "api_calls_fallback": 0}
            return ["*   Maybe it's \"졸았겠어?\" (Did I doze off?)."]

    module = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    module._get_ai_translator = lambda: _DummyAI()

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="W",
    )
    ctx = TaskContext(
        image_path="/tmp/noise.png",
        source_language="korean",
        target_language="zh-CN",
        regions=[region],
    )

    asyncio.run(module.process(ctx))

    assert (ctx.regions[0].target_text or "").strip() == "[INPAINT_ONLY]"
