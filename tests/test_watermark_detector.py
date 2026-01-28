from core.models import Box2D, RegionData


def test_watermark_detector_keyword_case_insensitive():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=100, y2=50), source_text="MangaForFree.COM"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is True


def test_watermark_detector_position_short_text_not_watermark():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=5, y1=950, x2=120, y2=980), source_text="note"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is False


def test_watermark_detector_near_edge_with_keyword():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=5, y1=950, x2=200, y2=980), source_text="mangaforfree.com"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is True


def test_watermark_detector_cross_page_repeat():
    from core.watermark_detector import WatermarkDetector

    detector = WatermarkDetector()
    regions_page1 = [RegionData(box_2d=Box2D(x1=300, y1=500, x2=420, y2=530), source_text="note")]
    regions_page2 = [RegionData(box_2d=Box2D(x1=305, y1=502, x2=425, y2=532), source_text="note")]

    detector.detect(regions_page1, image_shape=(1000, 800))
    result = detector.detect(regions_page2, image_shape=(1000, 800))

    assert result[0].is_watermark is True


def test_watermark_detector_sets_inpaint_mode():
    from core.watermark_detector import WatermarkDetector

    region = RegionData(box_2d=Box2D(x1=5, y1=950, x2=120, y2=980), source_text="mangaforfree")
    detector = WatermarkDetector()
    result = detector.detect([region], image_shape=(1000, 800))

    assert result[0].inpaint_mode == "erase"


def test_translator_skips_watermark_region():
    import asyncio

    from core.models import TaskContext
    from core.modules.translator import TranslatorModule

    region = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=100, y2=40),
        source_text="watermark",
        is_watermark=True,
    )
    ctx = TaskContext(image_path="/tmp/input.png", regions=[region])
    module = TranslatorModule(use_mock=True)

    result = asyncio.run(module.process(ctx))

    assert result.regions[0].target_text == ""
