from core.models import Box2D, RegionData
from core.translator import group_adjacent_regions
from core.models import TaskContext
from core.modules.translator import TranslatorModule


def test_group_adjacent_regions_merges_same_line_segments():
    left = RegionData(
        box_2d=Box2D(x1=149, y1=2389, x2=257, y2=2440),
        source_text="그동안",
        confidence=0.9,
    )
    right = RegionData(
        box_2d=Box2D(x1=255, y1=2390, x2=412, y2=2433),
        source_text="일방적으로",
        confidence=0.9,
    )

    groups = group_adjacent_regions([left, right])

    assert len(groups) == 1
    assert {r.source_text for r in groups[0]} == {"그동안", "일방적으로"}


def test_translator_skips_numeric_noise_within_group():
    left = RegionData(
        box_2d=Box2D(x1=149, y1=2389, x2=257, y2=2440),
        source_text="그동안",
        confidence=0.9,
    )
    right = RegionData(
        box_2d=Box2D(x1=255, y1=2390, x2=412, y2=2433),
        source_text="일방적으로",
        confidence=0.9,
    )
    noise = RegionData(
        box_2d=Box2D(x1=269, y1=2422, x2=295, y2=2445),
        source_text="2",
        confidence=0.9,
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[left, right, noise])
    module = TranslatorModule(use_mock=True)

    result = __import__("asyncio").run(module.process(ctx))
    translated = [r for r in result.regions if r.target_text and not r.target_text.startswith("[INPAINT_ONLY]")]
    assert len(translated) == 1
    assert "2" not in translated[0].target_text
