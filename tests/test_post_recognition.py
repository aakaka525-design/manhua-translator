import asyncio

from core.models import Box2D, RegionData


class _FakeEngine:
    def __init__(self):
        self.seen_boxes = []

    async def recognize(self, image_path, regions):
        for region in regions:
            self.seen_boxes.append(region.box_2d)
            region.source_text = "POSTREC"


def test_post_recognize_groups_uses_union_box():
    from core.vision.ocr.post_recognition import post_recognize_groups

    group = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="A",
            edge_role="current_top",
        ),
        RegionData(box_2d=Box2D(x1=8, y1=5, x2=20, y2=15), source_text="B"),
    ]
    groups = [group, [RegionData(source_text="NOBOX")]]
    engine = _FakeEngine()

    result = asyncio.run(post_recognize_groups("dummy.png", groups, engine))

    assert result == {0: "POSTREC"}
    assert engine.seen_boxes
    box = engine.seen_boxes[0]
    assert (box.x1, box.y1, box.x2, box.y2) == (0, 0, 20, 15)


def test_post_recognize_groups_filters_by_conditions():
    from core.vision.ocr.post_recognition import post_recognize_groups

    def _region(x1, y1, x2, y2, conf=0.9, edge_role=None):
        return RegionData(
            box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2),
            source_text="TXT",
            confidence=conf,
            edge_role=edge_role,
        )

    groups = [
        # multiline + low confidence -> include
        [_region(0, 0, 10, 10, conf=0.3), _region(0, 20, 10, 30, conf=0.3)],
        # low confidence only -> exclude
        [_region(0, 200, 10, 210, conf=0.3)],
        # edge + low confidence -> include
        [_region(0, 0, 10, 10, conf=0.3, edge_role="current_top")],
    ]
    engine = _FakeEngine()

    result = asyncio.run(
        post_recognize_groups("dummy.png", groups, engine, image_height=1000)
    )

    assert result == {0: "POSTREC", 2: "POSTREC"}
    assert len(engine.seen_boxes) == 2
