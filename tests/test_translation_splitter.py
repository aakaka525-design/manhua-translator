from core.translation_splitter import parse_top_bottom


def test_parse_top_bottom_json():
    text = '{"top":"Hello","bottom":"World"}'
    top, bottom = parse_top_bottom(text)
    assert top == "Hello"
    assert bottom == "World"


def test_parse_top_bottom_truncated_json_keeps_top():
    text = '{"top":"정말 내 몸이랑 연결된 거 같잖아…","bottom":"'
    top, bottom = parse_top_bottom(text)
    assert top == "정말 내 몸이랑 연결된 거 같잖아…"
    assert bottom == ""
