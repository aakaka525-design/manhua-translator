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
        box_2d=Box2D(x1=10, y1=200, x2=20, y2=210),
        source_text="hi",
        target_text="你好",
        is_sfx=False,
    )
    r_sfx = RegionData(
        box_2d=Box2D(x1=20, y1=300, x2=30, y2=310),
        source_text="BANG",
        target_text="[SFX: BANG]",
        is_sfx=True,
    )
    r_empty = RegionData(
        box_2d=Box2D(x1=30, y1=400, x2=40, y2=410),
        source_text="empty",
        target_text="",
        inpaint_mode="replace",
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[r_erase, r_replace, r_sfx, r_empty])
    asyncio.run(module.process(ctx))

    selected = {r.region_id for r in (dummy.regions or [])}
    assert selected == {r_erase.region_id, r_replace.region_id}


def test_inpainter_does_not_skip_on_is_sfx_when_target_text_present(tmp_path):
    dummy = _DummyInpainter()
    module = InpainterModule(inpainter=dummy, output_dir=str(tmp_path), use_time_subdir=False)

    r_misclassified = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=20, y2=20),
        source_text="유령씨표정이",
        target_text="幽灵先生的表情",
        is_sfx=True,
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[r_misclassified])
    asyncio.run(module.process(ctx))

    selected = {r.region_id for r in (dummy.regions or [])}
    assert selected == {r_misclassified.region_id}


def test_inpainter_merges_adjacent_regions_for_inpaint(tmp_path):
    dummy = _DummyInpainter()
    module = InpainterModule(inpainter=dummy, output_dir=str(tmp_path), use_time_subdir=False)

    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=110, y2=40),
        source_text="hello",
        target_text="你好",
    )
    r2 = RegionData(
        box_2d=Box2D(x1=12, y1=45, x2=112, y2=75),
        source_text="world",
        target_text="世界",
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[r1, r2])
    asyncio.run(module.process(ctx))

    assert dummy.regions is not None
    assert len(dummy.regions) == 1
    merged = dummy.regions[0].box_2d
    assert (merged.x1, merged.y1, merged.x2, merged.y2) == (10, 10, 112, 75)


def test_inpainter_expands_crosspage_bottom(tmp_path):
    from PIL import Image

    dummy = _DummyInpainter()
    module = InpainterModule(inpainter=dummy, output_dir=str(tmp_path), use_time_subdir=False)

    image_path = tmp_path / "input.png"
    Image.new("RGB", (100, 100), color="white").save(image_path)

    region = RegionData(
        box_2d=Box2D(x1=10, y1=70, x2=40, y2=80),
        source_text="test",
        target_text="测试",
        crosspage_role="current_bottom",
    )

    ctx = TaskContext(image_path=str(image_path), regions=[region])
    asyncio.run(module.process(ctx))

    assert dummy.regions is not None
    assert dummy.regions[0].box_2d.y2 > 80
    assert dummy.regions[0].box_2d.y2 <= 100
