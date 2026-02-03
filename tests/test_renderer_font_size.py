from pathlib import Path

from PIL import Image

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
    assert 15 <= size <= 30  # Relaxed range for font estimation algorithm
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
    assert 14 <= size <= 40  # Relaxed range for fallback estimation


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


def test_fit_text_reference_wraps_long_text_when_min_size_too_large():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=251, y2=88)
    text = "最重要的是，因为我的缘故，幽灵先生那焦灼的表情"
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text=text,
        box=box,
        ref_size=35,
        ref_source="estimate",
    )
    assert len(lines) > 1
    assert meta["font_size_relaxed"] is True


def test_estimate_font_size_applies_bias_and_compact_spacing():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=240, y2=80)
    text_length = 24
    size_default = renderer.style_estimator.estimate_font_size(
        box=box,
        text_length=text_length,
    )
    size_biased = renderer.style_estimator.estimate_font_size(
        box=box,
        text_length=text_length,
        bias=1.1,
    )
    assert size_biased > size_default

    size_compact = renderer.style_estimator.estimate_font_size(
        box=box,
        text_length=text_length,
        line_spacing=1.2,
        line_spacing_compact=1.1,
        compact_threshold=0.9,
    )
    assert size_compact >= size_default


def test_renderer_sets_font_size_metadata(tmp_path: Path):
    img_path = tmp_path / "src.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=200, y2=80),
        source_text="你好",
        target_text="你好",
    )
    renderer = TextRenderer()
    renderer._render_sync(
        image_path=str(img_path),
        regions=[region],
        output_path=str(tmp_path / "out.png"),
        original_image_path=str(img_path),
    )

    assert region.font_size_ref is not None
    assert region.font_size_used is not None
    assert region.font_size_source in {"estimate", "override", "fallback"}


def test_renderer_uses_render_box_for_layout(tmp_path: Path):
    img_path = tmp_path / "src.png"
    Image.new("RGB", (200, 120), "white").save(img_path)

    region = RegionData(
        box_2d=Box2D(x1=0, y1=60, x2=100, y2=120),
        source_text="测试文本",
        target_text="测试文本测试文本",
    )
    region.render_box_2d = Box2D(x1=0, y1=0, x2=200, y2=120)

    renderer = TextRenderer()
    renderer._render_sync(
        image_path=str(img_path),
        regions=[region],
        output_path=str(tmp_path / "out.png"),
        original_image_path=str(img_path),
    )

    expected_ref = renderer.style_estimator.estimate_font_size(
        region.render_box_2d,
        len(region.source_text),
        line_spacing=renderer.line_spacing,
        line_spacing_compact=renderer.line_spacing_compact,
        compact_threshold=renderer.line_spacing_compact_threshold,
        bias=renderer.style_config.font_size_estimate_bias,
    )
    expected_size, _, _ = renderer.fit_text_to_box_with_reference(
        text=region.target_text,
        box=region.render_box_2d,
        ref_size=expected_ref,
        ref_source="estimate",
    )
    assert region.font_size_used == expected_size
