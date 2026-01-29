from __future__ import annotations

from typing import List

from .models import Box2D, RegionData, TaskContext
from .translator import group_adjacent_regions


def _group_box(group: List[RegionData]) -> Box2D:
    xs = [r.box_2d.x1 for r in group if r.box_2d]
    ys = [r.box_2d.y1 for r in group if r.box_2d]
    xe = [r.box_2d.x2 for r in group if r.box_2d]
    ye = [r.box_2d.y2 for r in group if r.box_2d]
    return Box2D(x1=min(xs), y1=min(ys), x2=max(xe), y2=max(ye))


def find_edge_groups(context: TaskContext, edge: str, ratio: float = 0.1):
    groups = group_adjacent_regions(context.regions)
    edge_groups = []
    for group in groups:
        if not any(r.box_2d for r in group):
            continue
        box = _group_box(group)
        if edge == "top" and box.y1 <= context.image_height * ratio:
            edge_groups.append((group, box))
        if edge == "bottom" and box.y2 >= context.image_height * (1 - ratio):
            edge_groups.append((group, box))
    return edge_groups


def match_crosspage_pairs(bottom_groups, top_groups, min_overlap: float = 0.2):
    pairs = []
    used = set()
    for bottom_group, bottom_box in bottom_groups:
        best = None
        best_score = 0
        for idx, (top_group, top_box) in enumerate(top_groups):
            if idx in used:
                continue
            overlap = max(0, min(bottom_box.x2, top_box.x2) - max(bottom_box.x1, top_box.x1))
            min_width = min(bottom_box.width, top_box.width)
            score = overlap / min_width if min_width > 0 else 0
            if score > best_score:
                best_score = score
                best = idx
        if best is not None and best_score >= min_overlap:
            used.add(best)
            pairs.append((bottom_group, top_groups[best][0]))
    return pairs
