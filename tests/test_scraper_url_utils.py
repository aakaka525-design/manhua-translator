from scraper.url_utils import infer_id, infer_url, parse_chapter_range


def test_infer_id_url():
    assert infer_id("https://example.com/webtoon/123") == "123"
    assert infer_id("abc") == "abc"


def test_infer_url_manga_and_chapter():
    base = "https://toongod.org"
    assert infer_url(base, "123", "manga") == "https://toongod.org/webtoon/123"
    assert (
        infer_url(base, "5", "chapter", manga_id="123")
        == "https://toongod.org/webtoon/123/5/"
    )


def test_parse_chapter_range_ordering():
    assert parse_chapter_range("1-3") == (1, 3)
    assert parse_chapter_range("10:2") == (2, 10)
