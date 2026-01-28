import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.inpainter import InpainterModule


class _DummyInpainter:
    def __init__(self):
        self.regions = None

    async def inpaint_regions(self, image_path, regions, output_path, temp_dir, dilation):
        self.regions = regions
        return output_path


def test_inpainter_selects_regions_for_erase_and_replace(tmp_path):
    dummy = _DummyInpainter()
    module = InpainterModule(inpainter=dummy, output_dir=str(tmp_path), use_time_subdir=False)

    r_erase = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="wm",
        target_text="",
        inpaint_mode="erase",
    )
    r_replace = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=20, y2=20),
        source_text="hi",
        target_text="你好",
        is_sfx=False,
    )
    r_sfx = RegionData(
        box_2d=Box2D(x1=20, y1=20, x2=30, y2=30),
        source_text="BANG",
        target_text="[SFX: BANG]",
        is_sfx=True,
    )
    r_empty = RegionData(
        box_2d=Box2D(x1=30, y1=30, x2=40, y2=40),
        source_text="empty",
        target_text="",
        inpaint_mode="replace",
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[r_erase, r_replace, r_sfx, r_empty])
    asyncio.run(module.process(ctx))

    selected = {r.region_id for r in (dummy.regions or [])}
    assert selected == {r_erase.region_id, r_replace.region_id}
