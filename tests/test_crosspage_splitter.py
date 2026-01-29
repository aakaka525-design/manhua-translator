from core.crosspage_splitter import split_by_punctuation


def test_split_by_punctuation_prefers_midpoint():
    text = "这段时间，单方面地让我很难受。"
    top, bottom = split_by_punctuation(text)
    assert top.endswith("，")
    assert bottom.startswith("单方面")


def test_split_by_punctuation_fallback_ratio():
    text = "没有标点的长句测试"
    top, bottom = split_by_punctuation(text)
    assert top
    assert bottom
    assert abs(len(top) - len(bottom)) <= 2
