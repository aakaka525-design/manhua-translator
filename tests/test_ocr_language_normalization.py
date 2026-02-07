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


def test_get_cached_ocr_retries_without_show_log_when_unsupported(monkeypatch):
    import sys

    from core.vision.ocr import cache as cache_mod

    init_calls = []

    class DummyOCR:
        def __init__(self, *args, **kwargs):
            init_calls.append(dict(kwargs))
            if "show_log" in kwargs:
                raise ValueError("Unknown argument: show_log")
            self.kwargs = kwargs
            self.lang = kwargs.get("lang")

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=DummyOCR))
    cache_mod._ocr_cache.clear()

    ocr = cache_mod.get_cached_ocr("en")

    assert ocr.lang == "en"
    assert ocr.kwargs["text_recognition_model_name"] == "en_PP-OCRv5_mobile_rec"
    assert len(init_calls) == 2
    assert "show_log" in init_calls[0]
    assert "show_log" not in init_calls[1]
