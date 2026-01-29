from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
from uuid import uuid4

from ..models import Box2D, RegionData

ROW_GAP_RATIO = 0.6
X_GAP_RATIO = 0.8
HEIGHT_RATIO = 0.5
MAX_HEIGHT_RATIO = 2.0
MIN_CONFIDENCE = 0.4


@dataclass
class _Row:
    regions: list[RegionData]
    center_y: float


def _median(values: list[int]) -> float:
    values = sorted(values)
    count = len(values)
    if count == 0:
        return 0.0
    mid = count // 2
    if count % 2 == 1:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


def _union_box(regions: Iterable[RegionData]) -> Box2D:
    xs = [r.box_2d.x1 for r in regions if r.box_2d]
    ys = [r.box_2d.y1 for r in regions if r.box_2d]
    xe = [r.box_2d.x2 for r in regions if r.box_2d]
    ye = [r.box_2d.y2 for r in regions if r.box_2d]
    return Box2D(x1=min(xs), y1=min(ys), x2=max(xe), y2=max(ye))


def _join_texts(texts: list[str]) -> str:
    out = ""
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if not out:
            out = text
            continue
        if out[-1].isascii() and text[0].isascii():
            out += " " + text
        else:
            out += text
    return out


def merge_line_regions(groups: list[list[RegionData]]) -> list[RegionData]:
    merged_regions: list[RegionData] = []

    for group in groups:
        candidates = [
            r
            for r in group
            if r.box_2d
            and r.source_text
            and not r.is_watermark
            and not r.is_sfx
            and r.confidence >= MIN_CONFIDENCE
        ]
        excluded = [r for r in group if r not in candidates]

        if len(candidates) <= 1:
            merged_regions.extend(group)
            continue

        heights = [r.box_2d.height for r in candidates if r.box_2d]
        if not heights:
            merged_regions.extend(group)
            continue

        median_h = _median(heights)
        if median_h <= 0:
            merged_regions.extend(group)
            continue
        if max(heights) / max(1, min(heights)) > MAX_HEIGHT_RATIO:
            merged_regions.extend(group)
            continue

        rows: list[_Row] = []
        for region in sorted(candidates, key=lambda r: (r.box_2d.y1, r.box_2d.x1)):
            center_y = (region.box_2d.y1 + region.box_2d.y2) / 2
            placed = False
            for row in rows:
                if abs(center_y - row.center_y) <= ROW_GAP_RATIO * median_h:
                    row.regions.append(region)
                    row.center_y = (
                        sum(
                            (r.box_2d.y1 + r.box_2d.y2) / 2 for r in row.regions
                        )
                        / len(row.regions)
                    )
                    placed = True
                    break
            if not placed:
                rows.append(_Row([region], center_y))

        rows.sort(key=lambda row: row.center_y)
        ordered: list[RegionData] = []
        for row in rows:
            row.regions.sort(key=lambda r: r.box_2d.x1)
            ordered.extend(row.regions)

        for left, right in zip(ordered, ordered[1:]):
            x_gap = right.box_2d.x1 - left.box_2d.x2
            if x_gap > X_GAP_RATIO * median_h:
                merged_regions.extend(group)
                break
        else:
            merged_text = _join_texts([r.source_text for r in ordered])
            base = max(
                ordered, key=lambda r: r.box_2d.width * r.box_2d.height
            )
            merged = base.model_copy(deep=True)
            merged.region_id = uuid4()
            merged.source_text = merged_text
            merged.normalized_text = merged_text
            merged.box_2d = _union_box(ordered)
            merged.render_box_2d = None
            merged.confidence = sum(r.confidence for r in ordered) / len(ordered)
            merged_regions.append(merged)
            merged_regions.extend(excluded)

    return merged_regions
