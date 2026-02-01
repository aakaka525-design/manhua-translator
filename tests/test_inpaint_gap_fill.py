import asyncio
from pathlib import Path

import cv2
import numpy as np

from core.models import Box2D, RegionData
from core.vision.inpainter import Inpainter


class _DummyInpainter(Inpainter):
    async def inpaint(self, image_path: str, mask_path: str, output_path: str) -> str:
        image = cv2.imread(image_path)
        cv2.imwrite(output_path, image)
        return output_path


def test_inpaint_regions_uses_env_gap_fill(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("INPAINT_GAP_FILL_PX", "8")

    called = {}

    def _spy_fill(self, mask, regions, height, width, max_gap=0, **kwargs):
        called["max_gap"] = max_gap
        return mask

    monkeypatch.setattr(_DummyInpainter, "_fill_vertical_gaps", _spy_fill, raising=True)

    img = np.full((60, 60, 3), 255, dtype=np.uint8)
    image_path = tmp_path / "img.png"
    cv2.imwrite(str(image_path), img)

    regions = [
        RegionData(box_2d=Box2D(x1=10, y1=10, x2=30, y2=20), source_text="line1"),
        RegionData(box_2d=Box2D(x1=12, y1=30, x2=32, y2=40), source_text="line2"),
    ]

    output_path = tmp_path / "out.png"
    asyncio.run(
        _DummyInpainter().inpaint_regions(
            image_path=str(image_path),
            regions=regions,
            output_path=str(output_path),
            temp_dir=str(tmp_path),
        )
    )

    assert called.get("max_gap") == 8


def test_fill_vertical_gaps_uses_expanded_boxes_for_small_regions() -> None:
    inpainter = _DummyInpainter()
    mask = np.zeros((200, 200), dtype=np.uint8)
    regions = [
        RegionData(box_2d=Box2D(x1=40, y1=50, x2=140, y2=70), source_text="line1"),
        RegionData(box_2d=Box2D(x1=60, y1=90, x2=130, y2=108), source_text="line2"),
    ]

    out = inpainter._fill_vertical_gaps(mask, regions, 200, 200, max_gap=8)

    assert out[82, 70] == 255
