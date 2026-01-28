from core.models import Box2D, RegionData


def test_watermark_detector_keyword_case_insensitive():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=100, y2=50), source_text="MangaForFree.COM"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is True
