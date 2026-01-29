from core.models import Box2D, RegionData
from core.vision.ocr.postprocessing import merge_adjacent_text_regions


def test_merge_adjacent_text_regions_merges_same_line():
    r1 = RegionData(
        box_2d=Box2D(x1=100, y1=200, x2=160, y2=240),
        source_text="그",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=165, y1=202, x2=240, y2=242),
        source_text="동안",
        confidence=0.9,
    )

    merged = merge_adjacent_text_regions([r1, r2], max_gap_ratio=0.8, min_y_overlap=0.7)

    assert len(merged) == 1
    assert merged[0].source_text == "그동안"
    assert merged[0].box_2d.x1 == 100
    assert merged[0].box_2d.x2 == 240


def test_merge_adjacent_text_regions_skips_large_gap():
    r1 = RegionData(
        box_2d=Box2D(x1=100, y1=200, x2=160, y2=240),
        source_text="그",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=260, y1=202, x2=340, y2=242),
        source_text="동안",
        confidence=0.9,
    )

    merged = merge_adjacent_text_regions([r1, r2], max_gap_ratio=0.5, min_y_overlap=0.7)

    assert len(merged) == 2
