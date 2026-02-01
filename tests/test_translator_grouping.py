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


def test_group_adjacent_regions_does_not_merge_sfx_with_dialogue():
    sfx = RegionData(
        box_2d=Box2D(x1=100, y1=100, x2=150, y2=140),
        source_text="쿵!",
        confidence=0.9,
        is_sfx=True,
    )
    dialogue = RegionData(
        box_2d=Box2D(x1=120, y1=135, x2=300, y2=180),
        source_text="정말?",
        confidence=0.9,
        is_sfx=False,
    )

    groups = group_adjacent_regions([sfx, dialogue])

    assert len(groups) == 2


def test_group_adjacent_regions_allows_merge_with_partial_bubble_map():
    upper = RegionData(
        box_2d=Box2D(x1=391, y1=3462, x2=605, y2=3500),
        source_text="SHOWING MY",
        confidence=0.9,
    )
    lower = RegionData(
        box_2d=Box2D(x1=418, y1=3520, x2=571, y2=3538),
        source_text="BODY JUST LIKE",
        confidence=0.9,
    )

    bubble_map = {upper.region_id: 1}
    groups = group_adjacent_regions([upper, lower], bubble_map=bubble_map)

    assert len(groups) == 1


def test_group_adjacent_regions_does_not_merge_across_scripts():
    hangul = RegionData(
        box_2d=Box2D(x1=100, y1=100, x2=200, y2=130),
        source_text="높지각",
        confidence=0.9,
    )
    latin = RegionData(
        box_2d=Box2D(x1=102, y1=135, x2=202, y2=165),
        source_text="It's cold...",
        confidence=0.9,
    )

    groups = group_adjacent_regions([hangul, latin])

    assert len(groups) == 2


def test_group_adjacent_regions_respects_height_ratio():
    tall = RegionData(
        box_2d=Box2D(x1=100, y1=100, x2=200, y2=200),
        source_text="A",
        confidence=0.9,
    )
    short = RegionData(
        box_2d=Box2D(x1=110, y1=205, x2=190, y2=245),
        source_text="B",
        confidence=0.9,
    )

    groups = group_adjacent_regions([tall, short], height_ratio=0.8)

    assert len(groups) == 2


def test_group_adjacent_regions_allows_line_merge_even_if_height_differs():
    upper = RegionData(
        box_2d=Box2D(x1=391, y1=3462, x2=605, y2=3500),
        source_text="WHERE'S THE",
        confidence=0.9,
    )
    lower = RegionData(
        box_2d=Box2D(x1=418, y1=3520, x2=571, y2=3538),
        source_text="OLAINKEI!",
        confidence=0.9,
    )

    groups = group_adjacent_regions([upper, lower])

    assert len(groups) == 1
    assert {r.source_text for r in groups[0]} == {"WHERE'S THE", "OLAINKEI!"}


def test_group_adjacent_regions_respects_max_group_size():
    r1 = RegionData(
        box_2d=Box2D(x1=100, y1=100, x2=200, y2=140),
        source_text="A",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=105, y1=145, x2=205, y2=185),
        source_text="B",
        confidence=0.9,
    )
    r3 = RegionData(
        box_2d=Box2D(x1=110, y1=190, x2=210, y2=230),
        source_text="C",
        confidence=0.9,
    )

    groups = group_adjacent_regions([r1, r2, r3], max_group_size=2)

    assert [len(g) for g in groups] == [2, 1]


def test_group_adjacent_regions_default_overlap_is_strict():
    r1 = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=10),
        source_text="A",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=25, y1=12, x2=125, y2=22),
        source_text="B",
        confidence=0.9,
    )

    groups = group_adjacent_regions([r1, r2])

    assert len(groups) == 2


def test_group_adjacent_regions_default_overlap_is_very_strict():
    r1 = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=10),
        source_text="A",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=15, y1=12, x2=115, y2=22),
        source_text="B",
        confidence=0.9,
    )

    groups = group_adjacent_regions([r1, r2])

    assert len(groups) == 2


def test_group_adjacent_regions_default_y_gap_is_more_lenient():
    top = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=100),
        source_text="A",
        confidence=0.9,
    )
    bottom = RegionData(
        box_2d=Box2D(x1=0, y1=150, x2=100, y2=250),
        source_text="B",
        confidence=0.9,
    )

    groups = group_adjacent_regions([top, bottom])

    assert len(groups) == 1
