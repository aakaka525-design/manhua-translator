"""OCR subpackage exposing engines and utilities."""

from .base import OCREngine
from .cache import get_cached_ocr, suppress_native_stderr
from .paddle_engine import PaddleOCREngine, MockOCREngine

__all__ = [
    "OCREngine",
    "PaddleOCREngine",
    "MockOCREngine",
    "get_cached_ocr",
    "suppress_native_stderr",
]
