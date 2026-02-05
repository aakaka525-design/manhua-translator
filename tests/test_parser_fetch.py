from fastapi.testclient import TestClient


def test_parser_fetch_uses_scraper_fetch(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "temp").mkdir(exist_ok=True)
    (tmp_path / "app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app
    import scraper.fetch as scraper_fetch

    calls = {}

    def fake_fetch(url: str, mode: str = "http") -> str:
        calls["url"] = url
        calls["mode"] = mode
        return "<html><title>Test</title><body><p>Hello</p></body></html>"

    monkeypatch.setattr(scraper_fetch, "fetch_html", fake_fetch)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/parser/parse",
            json={"url": "https://example.com/article", "mode": "http"},
        )
        assert resp.status_code == 200

    assert calls == {"url": "https://example.com/article", "mode": "http"}
