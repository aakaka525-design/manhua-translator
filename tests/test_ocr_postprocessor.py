import pytest

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


def test_ocr_postprocessor_korean_corrections():
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="이닌 억은",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="korean")

    assert processed[0].normalized_text == "이번 역은"


@pytest.mark.parametrize("text", [
    "BANG!",
    "砰！",
    "咔嚓",
    "ドキドキ",
    "쾅!",
])
def test_ocr_postprocessor_marks_sfx(text):
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=text,
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].is_sfx is True
