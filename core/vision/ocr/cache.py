"""PaddleOCR instance cache and stderr suppression."""

import contextlib
import logging
import os
import sys
import threading
import warnings

# Reduce PaddleOCR/PaddlePaddle log noise
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["PADDLE_PDX_LOG_LEVEL"] = "ERROR"
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddlex").setLevel(logging.ERROR)

_ocr_cache: dict = {}
_ocr_lock = threading.Lock()


@contextlib.contextmanager
def suppress_native_stderr():
    """Suppress native stderr (NSLog) for OCR init."""
    if os.environ.get("OCR_SUPPRESS_NSLOG") == "0":
        yield
        return
    try:
        stderr_fd = sys.stderr.fileno()
    except Exception:
        yield
        return
    saved_stderr = os.dup(stderr_fd)
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, stderr_fd)
    os.close(devnull)
    try:
        yield
    finally:
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stderr)


def get_cached_ocr(lang: str = "en"):
    """
    Get or create cached PaddleOCR instance.

    Supports:
    - en: English (en_PP-OCRv5_mobile_rec)
    - korean: Korean (korean_PP-OCRv5_mobile_rec)
    """
    global _ocr_cache

    rec_model_map = {
        "en": "en_PP-OCRv5_mobile_rec",
        "korean": "korean_PP-OCRv5_mobile_rec",
    }
    rec_model = rec_model_map.get(lang, "en_PP-OCRv5_mobile_rec")

    if lang not in _ocr_cache:
        with _ocr_lock:
            if lang not in _ocr_cache:
                with suppress_native_stderr():
                    from paddleocr import PaddleOCR

                    _ocr_cache[lang] = PaddleOCR(
                        lang=lang,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name=rec_model,
                    )

    return _ocr_cache[lang]
