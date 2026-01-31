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


def test_watermark_detector_does_not_flag_dialogue_near_edge():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=200, y1=2, x2=550, y2=60),
            source_text="연결된 거 같잖아…",
        ),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1500, 800))

    assert result[0].is_watermark is False


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


def test_watermark_detector_korean_keywords():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=550, y1=1400, x2=690, y2=1420),
            source_text="입분양국뉴토끼469",
        ),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1500, 800))

    assert result[0].is_watermark is True


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


def test_watermark_detector_logs_summary(caplog):
    import logging
    from core.watermark_detector import WatermarkDetector

    caplog.set_level(logging.DEBUG)
    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=100, y2=50), source_text="mangaforfree.com"),
        RegionData(box_2d=Box2D(x1=10, y1=10, x2=120, y2=60), source_text="Hello"),
    ]
    WatermarkDetector().detect(regions, image_shape=(1000, 800))

    assert any("watermark" in record.message.lower() for record in caplog.records)


def test_watermark_detector_marks_newtoki_domain():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
            source_text="NEWTOKIJGOCOM",
        )
    ]
    WatermarkDetector().detect(regions, image_shape=(1000, 800))

    assert regions[0].is_watermark is True
    assert regions[0].inpaint_mode == "erase"


def test_watermark_detector_compact_keyword():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=120, y2=40),
            source_text="뉴 토끼 469",
        )
    ]
    WatermarkDetector().detect(regions, image_shape=(1000, 800))

    assert regions[0].is_watermark is True
    assert regions[0].inpaint_mode == "erase"


def test_watermark_detector_marks_newtok_typo():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=120, y2=40),
            source_text="NEWTOKOE",
        )
    ]
    WatermarkDetector().detect(regions, image_shape=(1000, 800))

    assert regions[0].is_watermark is True
    assert regions[0].inpaint_mode == "erase"


def test_watermark_detector_marks_edge_short_numeric_text():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(
            box_2d=Box2D(x1=2, y1=980, x2=80, y2=995),
            source_text="양국469",
        )
    ]
    WatermarkDetector().detect(regions, image_shape=(1000, 800))

    assert regions[0].is_watermark is True
    assert regions[0].inpaint_mode == "erase"
