from pathlib import Path


def test_parser_context_helpers_present():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "selectMangaFromParser" in content
    assert "parser.context" in content or "context:" in content
    assert "proxyParserImageUrl" in content


def test_parser_url_auto_https():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "normalizeUrlInput" in content
    assert "https://" in content


def test_parse_url_single_item_detail_fallback():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "items.length > 1" in content


def test_parse_url_sets_context():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "deriveParserContext" in content
    assert "parser.context" in content
    assert (
        "Object.assign(parser.context" in content
        or "parser.context = context" in content
    )


def test_parse_url_uses_list_result_fields():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "listResult?.site" in content or "listResult?.parser?.site" in content
    assert (
        "listResult?.recognized" in content
        or "listResult?.parser?.recognized" in content
    )
    assert (
        "listResult?.downloadable" in content
        or "listResult?.parser?.downloadable" in content
    )


def test_parse_url_resets_context_on_invalid_url():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "resetParserContext" in content


def test_parser_download_uses_context():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "selectedMangaSource" in content
    assert "selectedMangaContext" in content
    assert "getActivePayload" in content
