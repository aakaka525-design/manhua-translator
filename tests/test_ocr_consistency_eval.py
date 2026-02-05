from core.ocr_consistency_eval import normalize_for_compare, levenshtein_ratio


def test_normalize_for_compare_collapses_spaces_and_lowercases():
    text = "  Hello   World\n"
    assert normalize_for_compare(text) == "hello world"


def test_levenshtein_ratio_basic():
    assert levenshtein_ratio("abc", "abc") == 1.0
    assert levenshtein_ratio("abc", "ab") == 1 - 1 / 3
