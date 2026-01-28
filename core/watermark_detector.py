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

    def detect(self, regions: List[RegionData], image_shape: Tuple[int, int]):
        for r in regions:
            text = (r.source_text or "").lower()
            if any(k in text for k in self.keywords):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if r.box_2d:
                self._seen[text] = r.box_2d
        return regions
