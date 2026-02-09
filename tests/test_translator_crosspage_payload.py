import asyncio
import re

from core.crosspage_carryover import CrosspageCarryOverStore
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_crosspage_translation_uses_structured_payload_to_avoid_source_echo(
    tmp_path, monkeypatch
):
    """
    Regression (stress evidence):
    Gemini can return JSON like {"top":"<source>","bottom":"<translation>"} when the prompt does not
    define top/bottom semantics. For zh targets we must ensure both fields are translations and never
    leave Hangul in the assigned target_text.
    """
    monkeypatch.setenv("BUBBLE_GROUPING", "0")

    class _DummyAI:
        def __init__(self):
            self.seen_json_texts = []
            self.model = "dummy"
            self.last_metrics = {"api_calls": 0, "api_calls_fallback": 0}

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            self.last_metrics = {"api_calls": 1, "api_calls_fallback": 0}
            if output_format != "json":
                return ["OK" for _ in texts]

            self.seen_json_texts.extend(texts)

            out = []
            for t in texts:
                # If caller provides structured TOP/BOTTOM segments, emulate correct split translation.
                if "TOP:" in t and "BOTTOM:" in t:
                    out.append('{"top":"这","bottom":"是什么声音？"}')
                else:
                    # Emulate ambiguous prompt behavior: echo source in top, translate whole in bottom.
                    out.append('{"top":"이건 무슨 소리지?","bottom":"这是什么声音？"}')
            return out

    dummy = _DummyAI()
    module = TranslatorModule(source_lang="korean", target_lang="zh-CN", use_ai=True)
    module._get_ai_translator = lambda: dummy
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

    assert dummy.seen_json_texts, "expected crosspage JSON translation call"
    assert "TOP:" in dummy.seen_json_texts[0] and "BOTTOM:" in dummy.seen_json_texts[0]

    out = (ctx.regions[0].target_text or "").strip()
    assert re.search(r"[\u4e00-\u9fff]", out)
    assert not re.search(r"[\uac00-\ud7a3\u3130-\u318f\u1100-\u11ff]", out)

