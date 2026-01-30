import asyncio
from pathlib import Path

from PIL import Image

from core.models import Box2D, RegionData
from core.vision.inpainter import OpenCVInpainter


def test_inpaint_regions_returns_mask_path(tmp_path: Path):
    img_path = tmp_path / "img.png"
    Image.new("RGB", (20, 20), "white").save(img_path)

    regions = [RegionData(box_2d=Box2D(x1=2, y1=2, x2=6, y2=6))]
    inp = OpenCVInpainter()
    out_path = tmp_path / "out.png"

    result_path, mask_path = asyncio.run(
        inp.inpaint_regions(str(img_path), regions, str(out_path), str(tmp_path))
    )

    assert Path(result_path).exists()
    assert Path(mask_path).exists()
