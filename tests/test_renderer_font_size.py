from core.models import Box2D, RegionData
from core.renderer import TextRenderer


def test_region_font_size_metadata_defaults():
    region = RegionData()
    assert region.font_size_ref is None
    assert region.font_size_used is None
    assert region.font_size_relaxed is False
    assert region.font_size_source is None


def test_fit_text_reference_range():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=200, y2=80)
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text="你好世界",
        box=box,
        ref_size=20,
        ref_source="estimate",
    )
    assert 17 <= size <= 23
    assert meta["font_size_ref"] == 20
    assert meta["font_size_relaxed"] is False


def test_fit_text_reference_fallback():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=200, y2=80)
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text="你好世界",
        box=box,
        ref_size=None,
        ref_source="estimate",
    )
    assert meta["font_size_source"] == "fallback"
    assert 16 <= size <= 32


def test_fit_text_reference_relaxes_when_needed():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=80, y2=20)
    text = "这是一个非常非常长的文本需要被缩小"
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text=text,
        box=box,
        ref_size=20,
        ref_source="estimate",
    )
    assert meta["font_size_relaxed"] is True
    assert size < int(round(20 * 0.85))
