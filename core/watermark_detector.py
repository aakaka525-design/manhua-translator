import logging
import os
import re
from typing import Iterable, List, Optional, Tuple

from .models import RegionData

logger = logging.getLogger(__name__)


class WatermarkDetector:
    _DOMAIN_LIKE_RE = re.compile(r"^[a-z0-9]{4,}(com|net|org)$")
    _SHORT_TEXT_RE = re.compile(r"^[^\s]{2,12}\d{1,4}$")

    def __init__(self, keywords: Optional[Iterable[str]] = None):
        default_keywords = {
            "mangaforfree",
            "toongod",
            "newtoki",
            "newtok",
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
            "뉴토끼",
            "입분양",
            "입제공",
            "사이트",
        }
        self.keywords = {k.lower() for k in (keywords or default_keywords)}
        self._seen = {}

    def _normalize_text(self, text: str) -> tuple[str, str]:
        lower = text.lower()
        compact = re.sub(r"[\s\.\-_:·•]+", "", lower)
        return lower, compact

    def _near_edge(self, box, shape: Tuple[int, int]) -> bool:
        h, w = shape
        margin_x = w * 0.1
        margin_y = h * 0.1
        return box.x1 <= margin_x or box.x2 >= w - margin_x or box.y1 <= margin_y or box.y2 >= h - margin_y

    def _similar_pos(self, box, prev_box, tol: int = 20) -> bool:
        return abs(box.x1 - prev_box.x1) < tol and abs(box.y1 - prev_box.y1) < tol

    def detect(self, regions: List[RegionData], image_shape: Tuple[int, int]):
        debug = os.getenv("DEBUG_WATERMARK") == "1"
        for r in regions:
            raw_text = r.source_text or ""
            text, compact = self._normalize_text(raw_text)
            text_key = compact or text
            matched = any(k in text for k in self.keywords) or any(k in compact for k in self.keywords)
            if debug:
                logger.info(
                    "[watermark] text=%s compact=%s matched=%s box=%s",
                    text,
                    compact,
                    matched,
                    r.box_2d.model_dump() if r.box_2d else None,
                )
            if matched:
                r.is_watermark = True
                r.inpaint_mode = "erase"
                if r.box_2d:
                    self._seen[text_key] = r.box_2d
                continue
            if text_key in self._seen and r.box_2d and self._similar_pos(r.box_2d, self._seen[text_key]):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if not r.is_watermark and text_key and self._DOMAIN_LIKE_RE.match(text_key):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if (
                not r.is_watermark
                and text_key
                and r.box_2d
                and self._near_edge(r.box_2d, image_shape)
                and self._SHORT_TEXT_RE.match(text_key)
            ):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if r.box_2d:
                self._seen[text_key] = r.box_2d
        watermark_count = sum(1 for r in regions if getattr(r, "is_watermark", False))
        logger.debug(
            "watermark detector summary: total=%s watermarks=%s",
            len(regions),
            watermark_count,
        )
        return regions
