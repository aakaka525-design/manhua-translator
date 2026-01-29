from core.models import Box2D, RegionData, TaskContext
from core.crosspage_pairing import find_edge_groups, match_crosspage_pairs


def _region(x1, y1, x2, y2, text):
    return RegionData(box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2), source_text=text)


def test_match_crosspage_pairs_by_x_overlap():
    ctx_top = TaskContext(image_path="/tmp/top.png")
    ctx_top.image_height = 1000
    ctx_top.image_width = 800
    ctx_top.regions = [
        _region(100, 900, 300, 980, "bottom text"),
    ]

    ctx_bottom = TaskContext(image_path="/tmp/bottom.png")
    ctx_bottom.image_height = 1000
    ctx_bottom.image_width = 800
    ctx_bottom.regions = [
        _region(110, 10, 310, 90, "top text"),
    ]

    top_groups = find_edge_groups(ctx_top, edge="bottom")
    bottom_groups = find_edge_groups(ctx_bottom, edge="top")
    pairs = match_crosspage_pairs(top_groups, bottom_groups)
    assert len(pairs) == 1
