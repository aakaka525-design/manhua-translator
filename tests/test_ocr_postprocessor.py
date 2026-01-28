import asyncio
from unittest.mock import AsyncMock

import pytest

from core.models import Box2D, RegionData
from core.models import TaskContext
from core.modules.ocr import OCRModule


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


def test_ocr_postprocessor_korean_dialogue_not_sfx():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="유령씨표정이",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="korean")

    assert processed[0].is_sfx is False


@pytest.mark.parametrize("text", [
    "BANG!",
    "砰！",
    "咔嚓",
    "ドキドキ",
    "쾅!",
    "두근두근",
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


def test_ocr_postprocessor_does_not_mark_korean_phrase_as_sfx():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="유령씨표정이",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="korean")

    assert processed[0].is_sfx is False


@pytest.mark.parametrize(
    "text, expected_norm, expected_sfx",
    [
        ("", "", False),
        ("   ", "", False),
        ("...", "...", False),
        ("!!!", "!!!", True),
        ("LONG   TEXT   HERE", "LONG TEXT HERE", False),
    ],
)
def test_ocr_postprocessor_edge_cases(text, expected_norm, expected_sfx):
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=text,
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].normalized_text == expected_norm
    assert processed[0].is_sfx is expected_sfx


def test_ocr_module_applies_postprocessor():
    module = OCRModule(use_mock=True)
    module.engine.lang = "en"
    module.engine.detect_and_recognize = AsyncMock(return_value=[
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="  Hello  ",
            confidence=0.9,
        )
    ])

    ctx = TaskContext(image_path="/tmp/input.png")
    result = asyncio.run(module.process(ctx))

    assert result.regions[0].normalized_text == "Hello"
