import types


def test_get_cached_ocr_normalizes_korean_aliases(monkeypatch):
    import sys

    from core.vision.ocr import cache as cache_mod

    class DummyOCR:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self.lang = kwargs.get("lang")

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=DummyOCR))
    cache_mod._ocr_cache.clear()

    ocr = cache_mod.get_cached_ocr("ko")

    assert ocr.lang == "korean"
    assert ocr.kwargs["text_recognition_model_name"] == "korean_PP-OCRv5_mobile_rec"
    assert ocr.kwargs["show_log"] is False
