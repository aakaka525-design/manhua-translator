from core.models import Box2D, RegionData
from core.text_merge.line_merger import merge_line_regions


def test_line_merger_merges_same_row_fragments():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=100, x2=60, y2=130),
        source_text="너무",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=70, y1=102, x2=120, y2=132),
        source_text="좋아",
        confidence=0.9,
    )
    merged = merge_line_regions([[r1, r2]])

    assert len(merged) == 1
    assert merged[0].source_text == "너무좋아"
    assert merged[0].box_2d.x1 == 10
    assert merged[0].box_2d.x2 == 120
    assert merged[0].box_2d.y1 == 100
    assert merged[0].box_2d.y2 == 132


def test_line_merger_skips_watermark_regions():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=100, x2=60, y2=130),
        source_text="너무",
        confidence=0.9,
    )
    wm = RegionData(
        box_2d=Box2D(x1=500, y1=20, x2=680, y2=50),
        source_text="NEWTOKI",
        confidence=0.9,
        is_watermark=True,
    )
    merged = merge_line_regions([[r1, wm]])

    assert len(merged) == 2
    assert any(r.source_text == "NEWTOKI" for r in merged)


def test_line_merger_does_not_merge_when_height_diff_large():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=100, x2=60, y2=130),
        source_text="너무",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=70, y1=100, x2=180, y2=200),
        source_text="좋아",
        confidence=0.9,
    )
    merged = merge_line_regions([[r1, r2]])

    assert len(merged) == 2
