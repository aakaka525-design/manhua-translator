from app.routes import parser as parser_routes
from app.routes import scraper as scraper_routes
from scraper import url_utils


def test_routes_normalize_base_url_reuses_helper():
    assert parser_routes._normalize_base_url is url_utils.normalize_base_url
    assert scraper_routes._normalize_base_url is url_utils.normalize_base_url
