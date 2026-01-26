"""
OCR Engine - Compatibility layer.

This module re-exports from the new ocr subpackage for backward compatibility.
All new code should import from core.vision.ocr directly.
"""

# Re-export for backward compatibility
from .ocr import (
    OCREngine,
    PaddleOCREngine,
    get_cached_ocr,
    suppress_native_stderr,
)
from .ocr.paddle_engine import MockOCREngine

__all__ = [
    "OCREngine",
    "PaddleOCREngine",
    "MockOCREngine",
    "get_cached_ocr",
    "suppress_native_stderr",
]
