from __future__ import annotations

from typing import Dict, List

from ...models import Box2D, RegionData


LINE_GAP_RATIO = 0.6
LOW_CONF_THRESHOLD = 0.6
EDGE_BAND_RATIO = 0.15
EDGE_BAND_MIN = 128
EDGE_BAND_MAX = 256


def _union_box(regions: List[RegionData]) -> Box2D | None:
    boxes = [r.box_2d for r in regions if r.box_2d]
    if not boxes:
        return None
    x1 = min(b.x1 for b in boxes)
    y1 = min(b.y1 for b in boxes)
    x2 = max(b.x2 for b in boxes)
    y2 = max(b.y2 for b in boxes)
    return Box2D(x1=x1, y1=y1, x2=x2, y2=y2)


def _calc_band_height(image_height: int) -> int:
    if image_height <= 0:
        return 0
    base = max(EDGE_BAND_MIN, int(image_height * EDGE_BAND_RATIO))
    return min(image_height, min(base, EDGE_BAND_MAX))


def _median(values: list[int]) -> float:
    values = sorted(values)
    count = len(values)
    if count == 0:
        return 0.0
    mid = count // 2
    if count % 2 == 1:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


def _line_count(regions: List[RegionData]) -> int:
    boxes = [r.box_2d for r in regions if r.box_2d]
    if not boxes:
        return 0
    if len(boxes) == 1:
        return 1
    heights = [b.height for b in boxes]
    median_h = _median(heights)
    if median_h <= 0:
        return len(boxes)
    rows: list[float] = []
    for region in sorted(regions, key=lambda r: (r.box_2d.y1, r.box_2d.x1)):
        if not region.box_2d:
            continue
        center_y = (region.box_2d.y1 + region.box_2d.y2) / 2
        placed = False
        for idx, row_center in enumerate(rows):
            if abs(center_y - row_center) <= LINE_GAP_RATIO * median_h:
                rows[idx] = (row_center + center_y) / 2
                placed = True
                break
        if not placed:
            rows.append(center_y)
    return len(rows)


def _is_low_confidence(regions: List[RegionData], threshold: float) -> bool:
    confidences = [r.confidence for r in regions]
    if not confidences:
        return False
    avg_conf = sum(confidences) / len(confidences)
    return avg_conf < threshold


def _is_edge_region(regions: List[RegionData], image_height: int | None) -> bool:
    for region in regions:
        if getattr(region, "edge_role", None):
            return True
    if not image_height:
        return False
    box = _union_box(regions)
    if not box:
        return False
    band_height = _calc_band_height(image_height)
    return box.y1 <= band_height or box.y2 >= image_height - band_height


def _should_post_recognize(
    regions: List[RegionData],
    image_height: int | None,
    low_conf_threshold: float,
) -> bool:
    if not regions or not any(r.box_2d for r in regions):
        return False
    conditions = [
        _line_count(regions) >= 2,
        _is_low_confidence(regions, low_conf_threshold),
        _is_edge_region(regions, image_height),
    ]
    return sum(1 for cond in conditions if cond) >= 2


async def post_recognize_groups(
    image_path: str,
    groups: List[List[RegionData]],
    engine,
    image_height: int | None = None,
    low_conf_threshold: float = LOW_CONF_THRESHOLD,
) -> Dict[int, str]:
    """
    Re-run OCR recognition on merged group boxes and return overrides.

    Returns a mapping of group index -> recognized text.
    """
    if not image_path or not groups:
        return {}

    temp_regions: list[RegionData] = []
    group_indexes: list[int] = []

    for idx, group in enumerate(groups):
        if not _should_post_recognize(group, image_height, low_conf_threshold):
            continue
        box = _union_box(group)
        if not box:
            continue
        temp_regions.append(RegionData(box_2d=box, source_text=""))
        group_indexes.append(idx)

    if not temp_regions:
        return {}

    await engine.recognize(image_path, temp_regions)

    overrides: Dict[int, str] = {}
    for idx, region in zip(group_indexes, temp_regions):
        text = (region.source_text or "").strip()
        if text:
            overrides[idx] = text

    return overrides
