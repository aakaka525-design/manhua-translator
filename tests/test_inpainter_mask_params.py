from core.models import Box2D, RegionData
from core.vision.inpainter import mask_params_for_region


def test_mask_params_keeps_expand_for_inpaint_only_small_box():
    region = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=20, y2=20),
        source_text="OLAINKEI!",
        confidence=0.6,
    )
    region.target_text = "[INPAINT_ONLY]"

    expand, dilation = mask_params_for_region(region, base_expand=10, base_dilation=4)

    assert expand == 10
    assert dilation == 4
