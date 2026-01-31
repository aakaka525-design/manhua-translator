from pathlib import Path


def test_frontend_parser_list_endpoint_is_used():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "/api/v1/parser/list" in content


def test_frontend_parser_list_badges_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "已识别" in content
    assert "未识别" in content


def test_frontend_parser_context_label_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "解析站点" in content


def test_scraper_ui_optimized_components_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "ScraperConfig" in content
    assert "MangaListItem" in content
    assert "ChapterListItem" in content


def test_manga_list_item_props_bound():
    content = Path("frontend/src/views/scraper/MangaListItem.vue").read_text(
        encoding="utf-8"
    )
    assert "defineProps" in content
    assert "= defineProps" in content


def test_parser_detail_cover_uses_proxy():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "proxyParserImageUrl(scraper.parser.result.cover" in content


def test_chapter_clear_button_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "clearSelection" in content
