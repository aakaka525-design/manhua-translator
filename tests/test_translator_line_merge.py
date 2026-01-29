import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_merges_line_fragments_before_translate():
    ctx = TaskContext(image_path="/tmp/input.png")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=10, y1=100, x2=60, y2=130),
            source_text="너무",
            confidence=0.9,
        ),
        RegionData(
            box_2d=Box2D(x1=70, y1=102, x2=120, y2=132),
            source_text="좋아",
            confidence=0.9,
        ),
    ]
    module = TranslatorModule(use_mock=True)
    result = asyncio.run(module.process(ctx))

    merged_texts = [r.source_text for r in result.regions]
    assert "너무좋아" in merged_texts
