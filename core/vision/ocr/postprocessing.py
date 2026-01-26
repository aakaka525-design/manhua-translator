"""Post-processing utilities for OCR regions."""

from __future__ import annotations

import math
import re
from typing import cast
from uuid import uuid4

from ...models import Box2D, RegionData


def _box(region: RegionData) -> Box2D:
    """Return non-null Box2D or raise."""
    box = region.box_2d
    if box is None:
        raise ValueError("Region has no box_2d")
    return box


def filter_noise_regions(
    regions: list[RegionData],
    image_height: int = 0,
    relaxed: bool = False,
) -> list[RegionData]:
    """Filter noisy regions based on geometry and text patterns."""
    filtered: list[RegionData] = []

    for region in regions:
        if not region.box_2d or not region.source_text:
            continue

        box = region.box_2d
        text = region.source_text
        conf = region.confidence

        if not relaxed:
            # Size filter
            if box.width < 15 or box.height < 10:
                continue

            # Aspect ratio filter
            aspect_ratio = box.width / max(box.height, 1)
            if aspect_ratio > 20 or aspect_ratio < 0.05:
                continue

            # Short ASCII text needs high confidence
            if len(text) <= 3 and conf < 0.85 and text.isascii():
                continue

            # Pure numbers
            if re.match(r"^[0-9,\.]+$", text):
                is_price_like = (
                    len(text) >= 4
                    or "," in text
                    or (box.y1 > image_height * 0.8 if image_height else False)
                    or box.width > box.height * 3
                )
                if is_price_like:
                    continue

        # Common OCR noise
        if re.match(r"^[0OoSs]+$", text):
            continue

        # Domain/watermark
        if re.search(r"\.(com|net|org|io|cn)$", text, re.IGNORECASE):
            continue

        if re.match(r"^[A-Z]+SCANS?$", text) or re.match(r"^[A-Z]+COMICS?$", text):
            continue

        if not relaxed:
            if (
                text.isascii()
                and len(text) > 15
                and " " not in text
                and not re.search(r"[a-z]", text)
            ):
                continue

        # Noise patterns
        noise_patterns = [
            r"^[\-\u2212\u2013\u2014]+$",  # dashes
            r"^[I1l|]+$",  # vertical strokes
            r"^[\s\.]+$",  # spaces/dots
        ]
        if not relaxed:
            noise_patterns.extend(
                [
                    r"^[A-Za-z]$",  # single letter
                    r"^[A-Za-z][0-9]\.$",  # e.g. T0.
                    r"^[A-Z]{2}$",  # two caps
                    r"^[a-z][0-9]$",  # e.g. e0
                    r"^0+[A-Za-z]+$",  # leading zeros
                    r"^[A-Za-z]+0+$",  # trailing zeros
                ]
            )
        if any(re.match(p, text) for p in noise_patterns):
            continue

        filtered.append(region)

    return filtered


def remove_contained_regions(
    regions: list[RegionData],
    iou_threshold: float = 0.5,
) -> list[RegionData]:
    """Remove small regions heavily overlapped by larger ones."""
    if len(regions) <= 1:
        return regions

    sorted_regions = sorted(
        [r for r in regions if r.box_2d and r.source_text],
        key=lambda r: len(r.source_text or ""),
        reverse=True,
    )

    kept: list[RegionData] = []
    for region in sorted_regions:
        is_contained = False
        for kept_region in kept:
            box1, box2 = _box(region), _box(kept_region)
            x1 = max(box1.x1, box2.x1)
            y1 = max(box1.y1, box2.y1)
            x2 = min(box1.x2, box2.x2)
            y2 = min(box1.y2, box2.y2)

            if x2 <= x1 or y2 <= y1:
                continue

            inter_area = (x2 - x1) * (y2 - y1)
            area1 = box1.width * box1.height
            area2 = box2.width * box2.height

            smaller_area = min(area1, area2)
            overlap_ratio = inter_area / max(smaller_area, 1)

            if overlap_ratio > iou_threshold:
                is_contained = True
                break

        if not is_contained:
            kept.append(region)

    return kept


def geometric_cluster_dedup(regions: list[RegionData]) -> list[RegionData]:
    """Geometric clustering to deduplicate overlapping regions."""
    if len(regions) <= 1:
        return regions

    valid_regions = [r for r in regions if r.box_2d and r.source_text]
    if not valid_regions:
        return regions

    def get_features(r: RegionData):
        b = _box(r)
        return {
            "cx": (b.x1 + b.x2) / 2.0,
            "cy": (b.y1 + b.y2) / 2.0,
            "w": b.width,
            "h": b.height,
            "area": b.width * b.height,
        }

    def should_cluster(r1: RegionData, r2: RegionData) -> bool:
        b1, b2 = _box(r1), _box(r2)
        f1, f2 = get_features(r1), get_features(r2)

        ix1, iy1 = max(b1.x1, b2.x1), max(b1.y1, b2.y1)
        ix2, iy2 = min(b1.x2, b2.x2), min(b1.y2, b2.y2)
        if ix2 > ix1 and iy2 > iy1:
            inter = (ix2 - ix1) * (iy2 - iy1)
            union = f1["area"] + f2["area"] - inter
            iou = inter / max(union, 1)
            if iou > 0.3:
                return True

            containment = inter / max(min(f1["area"], f2["area"]), 1)
            if containment > 0.8:
                return True

            x_overlap = (ix2 - ix1) / max(min(f1["w"], f2["w"]), 1)
            y_overlap = (iy2 - iy1) / max(min(f1["h"], f2["h"]), 1)
            if x_overlap > 0.7 or y_overlap > 0.7:
                return True

        avg_size = (math.sqrt(f1["area"]) + math.sqrt(f2["area"])) / 2
        center_dist = math.sqrt((f1["cx"] - f2["cx"]) ** 2 + (f1["cy"] - f2["cy"]) ** 2)
        if center_dist < avg_size * 0.5:
            return True

        return False

    def get_score(r: RegionData) -> float:
        area = _box(r).width * _box(r).height
        text_len = len(r.source_text or "")
        conf = r.confidence or 0.5
        return conf * math.sqrt(area) * math.log(text_len + 2)

    clusters: list[list[RegionData]] = []
    for region in valid_regions:
        matched_clusters: list[int] = []
        for i, cluster in enumerate(clusters):
            for member in cluster:
                if should_cluster(region, member):
                    matched_clusters.append(i)
                    break

        if not matched_clusters:
            clusters.append([region])
        elif len(matched_clusters) == 1:
            clusters[matched_clusters[0]].append(region)
        else:
            new_cluster = [region]
            for i in sorted(matched_clusters, reverse=True):
                new_cluster.extend(clusters.pop(i))
            clusters.append(new_cluster)

    result: list[RegionData] = []
    for cluster in clusters:
        if len(cluster) == 1:
            result.append(cluster[0])
            continue

        sorted_cluster = sorted(cluster, key=get_score, reverse=True)
        best = sorted_cluster[0]
        best_text: str = best.source_text or ""
        for other in sorted_cluster[1:]:
            other_text: str = other.source_text or ""
            if best_text in other_text and get_score(other) * 0.8 > get_score(best):
                best = other
                break
        result.append(best)

    return result


def merge_group(group: list[RegionData]) -> RegionData:
    """Merge a group of regions into one."""
    if len(group) == 1:
        return group[0]

    valid_group = [r for r in group if r.box_2d]
    if not valid_group:
        return group[0]

    sorted_group = sorted(valid_group, key=lambda r: _box(r).x1)
    combined_text = " ".join(r.source_text for r in sorted_group if r.source_text)

    x1 = min(_box(r).x1 for r in sorted_group)
    y1 = min(_box(r).y1 for r in sorted_group)
    x2 = max(_box(r).x2 for r in sorted_group)
    y2 = max(_box(r).y2 for r in sorted_group)
    avg_conf = sum(r.confidence for r in sorted_group) / len(sorted_group)

    return RegionData(
        region_id=uuid4(),
        box_2d=Box2D(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2)),
        source_text=combined_text,
        confidence=avg_conf,
    )


def merge_line_regions_geometric(
    regions: list[RegionData],
    y_tolerance: float = 0.6,
) -> list[RegionData]:
    """Merge regions on the same line using geometry only."""
    if len(regions) <= 1:
        return regions

    valid_regions = [r for r in regions if r.box_2d and r.source_text]
    if not valid_regions:
        return regions

    groups: list[list[RegionData]] = []
    for region in valid_regions:
        box = _box(region)
        center_y = (box.y1 + box.y2) / 2.0

        matched_group = None
        for group in groups:
            boxes = [_box(r) for r in group if r.box_2d]
            if not boxes:
                continue
            group_center_y = sum((b.y1 + b.y2) / 2.0 for b in boxes) / len(boxes)
            avg_height = sum(b.height for b in boxes) / len(boxes)

            if abs(center_y - group_center_y) < avg_height * y_tolerance:
                matched_group = group
                break

        if matched_group:
            matched_group.append(region)
        else:
            groups.append([region])

    merged: list[RegionData] = []
    for group in groups:
        if len(group) == 1:
            merged.append(group[0])
        else:
            sorted_group = [r for r in group if r.box_2d]
            if not sorted_group:
                continue
            sorted_group = sorted(sorted_group, key=lambda r: _box(r).x1)
            combined_text = " ".join(
                r.source_text for r in sorted_group if r.source_text
            )
            x1 = min(_box(r).x1 for r in sorted_group)
            y1 = min(_box(r).y1 for r in sorted_group)
            x2 = max(_box(r).x2 for r in sorted_group)
            y2 = max(_box(r).y2 for r in sorted_group)
            avg_conf = sum(r.confidence for r in sorted_group) / len(sorted_group)
            merged.append(
                RegionData(
                    region_id=uuid4(),
                    box_2d=Box2D(x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2)),
                    source_text=combined_text,
                    confidence=avg_conf,
                )
            )

    return merged


def merge_line_regions(
    regions: list[RegionData],
    y_tolerance: float = 0.5,
) -> list[RegionData]:
    """Merge regions on the same line (legacy variant)."""
    if len(regions) <= 1:
        return regions

    valid_regions = [r for r in regions if r.box_2d and r.source_text]
    if not valid_regions:
        return regions

    groups: list[list[RegionData]] = []
    for region in valid_regions:
        box = _box(region)
        center_y = (box.y1 + box.y2) / 2

        matched_group = None
        for group in groups:
            for member in group:
                member_box = _box(member)
                member_center_y = (member_box.y1 + member_box.y2) / 2
                avg_height = (box.height + member_box.height) / 2
                y_diff = abs(center_y - member_center_y)
                if y_diff < avg_height * y_tolerance:
                    matched_group = group
                    break
            if matched_group:
                break

        if matched_group:
            matched_group.append(region)
        else:
            groups.append([region])

    merged: list[RegionData] = []
    for group in groups:
        if len(group) == 1:
            merged.append(group[0])
        else:
            sorted_group = sorted(group, key=lambda r: cast(Box2D, r.box_2d).x1)
            merged.append(merge_group(sorted_group))

    return merged


def merge_paragraph_regions(
    regions: list[RegionData],
    y_gap_ratio: float = 3.0,
    x_overlap_ratio: float = 0.15,
) -> list[RegionData]:
    """Merge vertically adjacent lines into paragraphs."""
    if len(regions) <= 1:
        return regions

    sorted_regions = sorted(
        [r for r in regions if r.box_2d],
        key=lambda r: (
            cast(Box2D, r.box_2d).y1,
            cast(Box2D, r.box_2d).x1,
        ),
    )
    if not sorted_regions:
        return regions

    merged: list[RegionData] = []
    current_group = [sorted_regions[0]]

    for region in sorted_regions[1:]:
        last = current_group[-1]
        last_box = _box(last)
        curr_box = _box(region)

        y_gap = curr_box.y1 - last_box.y2
        avg_height = (last_box.height + curr_box.height) / 2

        x_overlap_start = max(last_box.x1, curr_box.x1)
        x_overlap_end = min(last_box.x2, curr_box.x2)
        x_overlap = max(0, x_overlap_end - x_overlap_start)
        min_width = min(last_box.width, curr_box.width)
        x_overlap_pct = x_overlap / max(min_width, 1)

        is_vertically_close = (
            y_gap < avg_height * y_gap_ratio and y_gap > -avg_height * 0.5
        )
        has_x_overlap = x_overlap_pct > x_overlap_ratio

        if is_vertically_close and has_x_overlap:
            current_group.append(region)
        else:
            merged.append(merge_group(current_group))
            current_group = [region]

    if current_group:
        merged.append(merge_group(current_group))

    return merged


def deduplicate_regions(regions: list[RegionData]) -> list[RegionData]:
    """Remove duplicate regions based on text and IoU."""
    if not regions:
        return regions

    unique: list[RegionData] = []
    for region in regions:
        is_duplicate = False
        for existing in unique:
            if is_similar_region(region, existing):
                if region.confidence > existing.confidence:
                    unique.remove(existing)
                    unique.append(region)
                is_duplicate = True
                break
        if not is_duplicate:
            unique.append(region)

    return unique


def is_similar_region(r1: RegionData, r2: RegionData) -> bool:
    """Check if two regions are similar (same text + high IoU)."""
    if not r1.box_2d or not r2.box_2d:
        return r1.source_text == r2.source_text

    if r1.source_text != r2.source_text:
        return False

    b1, b2 = _box(r1), _box(r2)
    x1 = max(b1.x1, b2.x1)
    y1 = max(b1.y1, b2.y1)
    x2 = min(b1.x2, b2.x2)
    y2 = min(b1.y2, b2.y2)

    if x2 <= x1 or y2 <= y1:
        return False

    intersection = (x2 - x1) * (y2 - y1)
    area1 = b1.width * b1.height
    area2 = b2.width * b2.height
    union = area1 + area2 - intersection
    iou = intersection / union if union > 0 else 0
    return iou > 0.5
