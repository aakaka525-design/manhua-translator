import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_skips_prefilled_target():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hello",
        target_text="预先填充",
    )
    ctx = TaskContext(image_path="/tmp/x.png", regions=[region])
    module = TranslatorModule(use_mock=True)

    asyncio.run(module.process(ctx))

    assert ctx.regions[0].target_text == "预先填充"
