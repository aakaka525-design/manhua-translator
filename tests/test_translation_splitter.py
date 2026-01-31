from core.translation_splitter import parse_top_bottom


def test_parse_top_bottom_json():
    text = '{"top":"Hello","bottom":"World"}'
    top, bottom = parse_top_bottom(text)
    assert top == "Hello"
    assert bottom == "World"
