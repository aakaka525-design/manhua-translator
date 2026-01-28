import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_sets_render_box_for_grouped_regions():
    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=100, y2=20), source_text="A"),
        RegionData(box_2d=Box2D(x1=0, y1=30, x2=100, y2=50), source_text="B"),
        RegionData(box_2d=Box2D(x1=0, y1=60, x2=100, y2=80), source_text="C"),
    ]
    ctx = TaskContext(image_path="/tmp/input.png", regions=regions)
    module = TranslatorModule(use_mock=True)

    result = asyncio.run(module.process(ctx))

    render_region = next(
        r for r in result.regions if r.target_text and r.target_text != "[INPAINT_ONLY]"
    )
    assert render_region.render_box_2d is not None
    assert render_region.render_box_2d.x1 == 0
    assert render_region.render_box_2d.y1 == 0
    assert render_region.render_box_2d.x2 == 100
    assert render_region.render_box_2d.y2 == 80
