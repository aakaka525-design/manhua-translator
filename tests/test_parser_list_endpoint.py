from fastapi.testclient import TestClient


def test_list_endpoint_unrecognized_uses_generic_parser(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "temp").mkdir(exist_ok=True)
    (tmp_path / "app/static").mkdir(parents=True, exist_ok=True)

    html = """
    <html><body>
      <a href="/manga/one"><img src="/covers/one.jpg" alt="One" />One</a>
      <a href="/manga/two"><img src="/covers/two.jpg" alt="Two" />Two</a>
    </body></html>
    """

    from app.main import app
    import app.routes.parser as parser_routes

    monkeypatch.setattr(parser_routes, "fetch_html", lambda *_: html)

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/parser/list",
            json={"url": "https://unknown.example/list", "mode": "http"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_type"] == "list"
        assert data["recognized"] is False
        assert data["downloadable"] is False
        assert len(data["items"]) == 2
        assert any(
            item.get("title") == "One"
            and item.get("url") == "https://unknown.example/manga/one"
            and item.get("cover_url") == "https://unknown.example/covers/one.jpg"
            for item in data["items"]
        )
