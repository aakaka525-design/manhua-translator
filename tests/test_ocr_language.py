from core.vision.ocr.cache import normalize_ocr_lang


def test_normalize_ocr_lang_aliases_korean():
    assert normalize_ocr_lang("ko") == "korean"
    assert normalize_ocr_lang("KR") == "korean"
    assert normalize_ocr_lang("kor") == "korean"
    assert normalize_ocr_lang("korean") == "korean"


def test_normalize_ocr_lang_keeps_en():
    assert normalize_ocr_lang("en") == "en"
