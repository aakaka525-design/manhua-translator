import asyncio
from pathlib import Path

from core.crosspage_carryover import CrosspageCarryOverStore
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_crosspage_truncated_json_keeps_top_and_fallback_bottom(monkeypatch):
    class FakeAI:
        model = "fake"

        async def translate_batch(self, texts, output_format="numbered", contexts=None):
            if output_format == "json":
                return ['{"top":"上半句","bottom":"']
            return ["下半句"]

    module = TranslatorModule(use_mock=False, use_ai=True)
    monkeypatch.setattr(module, "_get_ai_translator", lambda: FakeAI())
    module._carryover_store = CrosspageCarryOverStore(Path("/tmp/_carryover.jsonl"))

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path="/tmp/x.png", target_language="zh-CN", regions=[region])
    ctx.crosspage_debug = {}
    asyncio.run(module.process(ctx))

    assert ctx.regions[0].target_text == "上半句"
    assert module._carryover_store.get("p1") == "下半句"
    assert ctx.crosspage_debug["translations"][0]["parse_error"] is None
