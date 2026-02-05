"""PaddleOCR instance cache and stderr suppression."""

import logging
import os
import threading
import warnings

from ...utils.stderr_suppressor import suppress_native_stderr

# Reduce PaddleOCR/PaddlePaddle log noise
warnings.filterwarnings("ignore", category=UserWarning)
os.environ["PADDLE_PDX_LOG_LEVEL"] = "ERROR"
logging.getLogger("ppocr").setLevel(logging.ERROR)
logging.getLogger("paddlex").setLevel(logging.ERROR)

_ocr_cache: dict = {}
_ocr_lock = threading.Lock()


def normalize_ocr_lang(lang: str) -> str:
    if not lang:
        return "en"
    value = str(lang).strip().lower()
    alias_map = {
        "ko": "korean",
        "kr": "korean",
        "kor": "korean",
    }
    return alias_map.get(value, value)


def get_cached_ocr(lang: str = "en"):
    """
    Get or create cached PaddleOCR instance.

    Supports:
    - en: English (en_PP-OCRv5_mobile_rec)
    - korean: Korean (korean_PP-OCRv5_mobile_rec)
    """
    global _ocr_cache

    lang_norm = normalize_ocr_lang(lang)
    rec_model_map = {
        "en": "en_PP-OCRv5_mobile_rec",
        "korean": "korean_PP-OCRv5_mobile_rec",
    }
    rec_model = rec_model_map.get(lang_norm, "en_PP-OCRv5_mobile_rec")

    if lang_norm not in _ocr_cache:
        with _ocr_lock:
            if lang_norm not in _ocr_cache:
                with suppress_native_stderr():
                    from paddleocr import PaddleOCR

                    _ocr_cache[lang_norm] = PaddleOCR(
                        lang=lang_norm,
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        text_detection_model_name="PP-OCRv5_mobile_det",
                        text_recognition_model_name=rec_model,
                    )

    return _ocr_cache[lang_norm]
