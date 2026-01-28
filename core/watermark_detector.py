from typing import Iterable, List, Optional, Tuple

from .models import RegionData


class WatermarkDetector:
    def __init__(self, keywords: Optional[Iterable[str]] = None):
        default_keywords = {
            "mangaforfree",
            "toongod",
            "manga",
            "manhua",
            "comic",
            "scan",
            "raw",
            "sub",
            "copyright",
            "all rights reserved",
            "©",
            "http",
            "https",
            ".com",
            ".net",
            ".org",
        }
        self.keywords = {k.lower() for k in (keywords or default_keywords)}
        self._seen = {}

    def _near_edge(self, box, shape: Tuple[int, int]) -> bool:
        h, w = shape
        margin_x = w * 0.1
        margin_y = h * 0.1
        return box.x1 <= margin_x or box.x2 >= w - margin_x or box.y1 <= margin_y or box.y2 >= h - margin_y

    def _similar_pos(self, box, prev_box, tol: int = 20) -> bool:
        return abs(box.x1 - prev_box.x1) < tol and abs(box.y1 - prev_box.y1) < tol

    def detect(self, regions: List[RegionData], image_shape: Tuple[int, int]):
        for r in regions:
            text = (r.source_text or "").lower()
            if any(k in text for k in self.keywords):
                r.is_watermark = True
                r.inpaint_mode = "erase"
                if r.box_2d:
                    self._seen[text] = r.box_2d
                continue
            if text in self._seen and r.box_2d and self._similar_pos(r.box_2d, self._seen[text]):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if r.box_2d and self._near_edge(r.box_2d, image_shape) and len(text) <= 20:
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if r.box_2d:
                self._seen[text] = r.box_2d
        return regions
