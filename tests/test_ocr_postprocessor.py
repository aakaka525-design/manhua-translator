from core.models import Box2D, RegionData


def test_ocr_postprocessor_normalizes_text():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="  Hello   World\n",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor

    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].normalized_text == "Hello World"
    assert processed[0].source_text == "  Hello   World\n"
