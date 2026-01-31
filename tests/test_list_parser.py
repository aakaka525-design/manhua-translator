from core.parser import list_parse


def test_list_parser_extracts_items():
    html = """
    <html><body>
      <a href="/manga/one">
        <img src="/covers/one.jpg" alt="One" />
        <span>One</span>
      </a>
      <a href="/manga/two">
        <img src="/covers/two.jpg" alt="Two" />
        <span>Two</span>
      </a>
    </body></html>
    """
    items = list_parse(html, "https://example.com")
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["url"] == "https://example.com/manga/one"
    assert items[0]["cover_url"] == "https://example.com/covers/one.jpg"


def test_list_parser_prefers_links_with_images_first():
    html = """
    <html><body>
      <a href="/manga/plain">Plain</a>
      <a href="/manga/with-image">
        <img src="/covers/with-image.jpg" alt="With Image" />
        <span>With Image</span>
      </a>
    </body></html>
    """
    items = list_parse(html, "https://example.com")
    assert items[0]["url"] == "https://example.com/manga/with-image"
