import json
from pathlib import Path

import numpy as np
import cv2

from core.models import Box2D, RegionData
from scripts import ocr_consistency_eval


class _FakeOCREngine:
    def __init__(self, lang: str = "en"):
        self.lang = lang

    async def detect_and_recognize(self, image_path: str):
        return [
            RegionData(
                box_2d=Box2D(x1=1, y1=1, x2=9, y2=9),
                source_text="Hello",
            )
        ]

    async def recognize(self, image_path: str, regions):
        for region in regions:
            region.source_text = "Hello"
        return regions


def _write_dummy(path: Path, size: int = 16):
    img = np.zeros((size, size, 3), dtype=np.uint8)
    cv2.imwrite(str(path), img)


def test_consistency_eval_writes_report(tmp_path):
    orig = tmp_path / "orig.png"
    upscaled = tmp_path / "up.png"
    _write_dummy(orig, 16)
    _write_dummy(upscaled, 32)

    out_path = tmp_path / "report.json"

    ocr_consistency_eval.main(
        [
            "--orig",
            str(orig),
            "--upscaled",
            str(upscaled),
            "--lang",
            "korean",
            "--out",
            str(out_path),
        ],
        engine_factory=_FakeOCREngine,
    )

    assert out_path.exists()
    data = json.loads(out_path.read_text())
    assert data["summary"]["total"] == 1
