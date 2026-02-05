from pathlib import Path

from app.routes.scraper import ScraperSearchRequest
import app.routes.scraper as scraper_routes


def test_coerce_rate_limit_rps_bounds():
    assert scraper_routes._coerce_rate_limit_rps(0.0) == 0.2
    assert scraper_routes._coerce_rate_limit_rps(0.1) == 0.2
    assert scraper_routes._coerce_rate_limit_rps(3.5) == 3.5
    assert scraper_routes._coerce_rate_limit_rps(50.0) == 20.0


def test_build_engine_propagates_rate_limit():
    request = ScraperSearchRequest(
        base_url="https://toongod.org",
        keyword="solo-leveling",
        rate_limit_rps=1.25,
    )
    engine, _ = scraper_routes._build_engine(request, Path("data"))
    assert engine.scraper.config.rate_limit_rps == 1.25
    assert engine.scraper.downloader.config.rate_limit_rps == 1.25
    assert engine.scraper.request_limiter is engine.scraper.downloader.request_limiter
