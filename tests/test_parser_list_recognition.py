def test_parse_catalog_url_extracts_path_page_and_orderby():
    from app.routes import parser as parser_routes

    path, page, orderby = parser_routes._parse_catalog_url(
        "https://toongod.org/webtoon/page/2/?m_orderby=views"
    )
    assert path == "/webtoon/"
    assert page == 2
    assert orderby == "views"


def test_recognize_site_matches_known_hosts():
    from app.routes import parser as parser_routes

    site, base_url = parser_routes._recognize_site("https://toongod.org/webtoon/")
    assert site == "toongod"
    assert base_url == "https://toongod.org"
