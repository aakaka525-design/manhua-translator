from __future__ import annotations

from .crosspage_pairing import find_edge_groups, match_crosspage_pairs
from .crosspage_splitter import split_by_punctuation


async def apply_crosspage_split(translator, ctx_a, ctx_b) -> None:
    bottom_groups = find_edge_groups(ctx_a, edge="bottom")
    top_groups = find_edge_groups(ctx_b, edge="top")
    pairs = match_crosspage_pairs(bottom_groups, top_groups)
    if not pairs:
        return

    for bottom_group, top_group in pairs:
        combined = " ".join(
            [r.source_text for r in bottom_group + top_group if r.source_text]
        )
        translation = (await translator.translate_texts([combined]))[0]
        top_text, bottom_text = split_by_punctuation(translation)

        def assign(group, text):
            largest = max(group, key=lambda r: r.box_2d.width * r.box_2d.height)
            largest.target_text = text
            for region in group:
                if region is not largest:
                    region.target_text = "[INPAINT_ONLY]"

        assign(bottom_group, top_text)
        assign(top_group, bottom_text)
