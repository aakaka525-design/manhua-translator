from pathlib import Path


def test_scraper_store_has_rate_limit_state_and_payload():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "rateLimitRps" in content
    assert "rate_limit_rps" in content


def test_scraper_config_view_exposes_rate_limit_input():
    content = Path("frontend/src/views/scraper/ScraperConfig.vue").read_text(
        encoding="utf-8"
    )
    assert "rateLimitRps" in content
    assert "自定义速率" in content or "每秒请求" in content


def test_scraper_config_view_exposes_rate_presets():
    content = Path("frontend/src/views/scraper/ScraperConfig.vue").read_text(
        encoding="utf-8"
    )
    assert "速率预设" in content
    assert "保守" in content
    assert "平衡" in content
    assert "快速" in content


def test_scraper_rate_presets_values():
    content = Path("frontend/src/views/scraper/ScraperConfig.vue").read_text(
        encoding="utf-8"
    )
    assert "value: 0.5" in content
    assert "value: 1" in content
    assert "value: 1.5" in content
