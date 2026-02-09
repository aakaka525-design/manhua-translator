import asyncio
import re

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_crosspage_top_text_retranslated_when_hangul_returned(tmp_path, monkeypatch):
    """
    Regression (stress run evidence): crosspage top_text could be assigned with Hangul for zh targets.
    We must not leave Hangul in target_text; prefer an AI re-translate rather than emitting failure markers.
    """
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    class _DummyAI:
        def __init__(self):
            self.calls_json = 0
            self.model = "dummy"
            self.last_metrics = {"api_calls": 0, "api_calls_fallback": 0}

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            self.last_metrics = {"api_calls": 1, "api_calls_fallback": 0}
            if output_format == "json":
                self.calls_json += 1
                if self.calls_json == 1:
                    return ['{"top":"이건 무슨 소리지?","bottom":""}' for _ in texts]
                return ['{"top":"这是什么声音？","bottom":""}' for _ in texts]
            return ["这是什么声音？" for _ in texts]

    dummy = _DummyAI()

    module = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    module._get_ai_translator = lambda: dummy
    from core.crosspage_carryover import CrosspageCarryOverStore

    module._carryover_store = CrosspageCarryOverStore(tmp_path / "carryover.jsonl")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="이건",
        crosspage_role="current_bottom",
        crosspage_pair_id="pair1",
        crosspage_texts=["무슨 소리지?"],
    )
    ctx = TaskContext(
        image_path="/tmp/crosspage.png",
        source_language="korean",
        target_language="zh-CN",
        regions=[region],
    )

    asyncio.run(module.process(ctx))

    out = (ctx.regions[0].target_text or "").strip()
    assert not out.startswith("[翻译失败]")
    assert re.search(r"[\u4e00-\u9fff]", out)
    assert not re.search(r"[\uac00-\ud7a3\u3130-\u318f\u1100-\u11ff]", out)
    assert dummy.calls_json >= 2
