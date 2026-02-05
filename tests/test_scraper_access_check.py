import pytest

from app.routes.scraper import ScraperAccessCheckRequest
import app.routes.scraper as scraper


class _DummyResponse:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummySession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get(self, *args, **kwargs):
        return _DummyResponse()


@pytest.mark.asyncio
async def test_access_check_uses_urlparse(monkeypatch):
    monkeypatch.setattr(scraper.aiohttp, "ClientSession", lambda *a, **k: _DummySession())
    request = ScraperAccessCheckRequest(base_url="https://example.com", path="/")
    response = await scraper.access_check(request)
    assert response.status == "ok"
