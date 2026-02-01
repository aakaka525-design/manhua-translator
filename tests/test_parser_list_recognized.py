from fastapi.testclient import TestClient


def test_list_endpoint_recognized_returns_downloadable(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "temp").mkdir(exist_ok=True)
    (tmp_path / "app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app
    import app.routes.parser as parser_routes

    async def fake_list_recognized(*_args, **_kwargs):
        return [
            {
                "id": "one",
                "title": "One",
                "url": "https://toongod.org/webtoon/one/",
                "cover_url": None,
            }
        ], []

    monkeypatch.setattr(parser_routes, "fetch_html", lambda *_: "<html></html>")
    monkeypatch.setattr(parser_routes, "_list_recognized_catalog", fake_list_recognized)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/parser/list", json={"url": "https://toongod.org/webtoon/"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recognized"] is True
        assert data["downloadable"] is True
        assert len(data["items"]) == 1


def test_list_endpoint_recognized_handles_engine_tuple(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "temp").mkdir(exist_ok=True)
    (tmp_path / "app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app
    import app.routes.parser as parser_routes
    import app.routes.scraper as scraper_routes

    class StubManga:
        id = "one"
        title = "One"
        url = "https://mangaforfree.com/manga/one/"
        cover_url = "https://mangaforfree.com/covers/one.jpg"

    class StubEngine:
        async def list_catalog(self, page=1, orderby=None, path=None):
            return ([StubManga()], True)

    def fake_build_engine(*_args, **_kwargs):
        return StubEngine(), None

    monkeypatch.setattr(parser_routes, "fetch_html", lambda *_: "<html></html>")
    monkeypatch.setattr(scraper_routes, "_build_engine", fake_build_engine)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/parser/list",
            json={"url": "https://mangaforfree.com/manga/no-mans-land"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["recognized"] is True
        assert data["downloadable"] is True
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == "one"
