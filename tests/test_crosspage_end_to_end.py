import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.pipeline import Pipeline


class _MockOCR:
    async def process(self, ctx):
        return ctx


class _MockTranslator:
    async def process(self, ctx):
        return ctx

    async def translate_texts(self, texts):
        return ["你好世界"]


class _MockInpainter:
    async def process(self, ctx):
        return ctx


class _MockRenderer:
    async def process(self, ctx):
        return ctx


def test_crosspage_split_end_to_end():
    top = TaskContext(image_path="/tmp/top.png")
    top.image_height = 1000
    top.image_width = 800
    top.regions = [
        RegionData(box_2d=Box2D(x1=100, y1=900, x2=300, y2=980), source_text="He")
    ]

    bottom = TaskContext(image_path="/tmp/bottom.png")
    bottom.image_height = 1000
    bottom.image_width = 800
    bottom.regions = [
        RegionData(box_2d=Box2D(x1=110, y1=10, x2=310, y2=90), source_text="llo")
    ]

    pipeline = Pipeline(
        ocr=_MockOCR(),
        translator=_MockTranslator(),
        inpainter=_MockInpainter(),
        renderer=_MockRenderer(),
    )

    results = asyncio.run(pipeline.process_batch_crosspage([top, bottom]))
    assert results[0].regions[0].target_text
    assert results[1].regions[0].target_text
