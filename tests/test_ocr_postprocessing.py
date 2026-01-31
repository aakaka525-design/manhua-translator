from core.models import Box2D, RegionData
from core.vision.ocr.postprocessing import (
    filter_noise_regions,
    geometric_cluster_dedup,
    merge_adjacent_text_regions,
)


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


def test_filter_noise_regions_keeps_domain_when_relaxed():
    region = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=200, y2=30),
        source_text="NEWTOKI.COM",
        confidence=0.9,
    )

    filtered = filter_noise_regions([region], image_height=2000, relaxed=True)

    assert len(filtered) == 1
    assert filtered[0].source_text == "NEWTOKI.COM"


def test_geometric_cluster_dedup_merges_overlapping_texts():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=60, y2=30),
        source_text="그동안",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=55, y1=12, x2=120, y2=32),
        source_text="일방적으로",
        confidence=0.9,
    )

    merged = geometric_cluster_dedup([r1, r2])

    assert len(merged) == 1
    assert "그동안" in merged[0].source_text
    assert "일방적으로" in merged[0].source_text
