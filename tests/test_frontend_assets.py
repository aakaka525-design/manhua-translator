from importlib import reload
from pathlib import Path
import sys

from fastapi.testclient import TestClient


def test_frontend_index_has_no_external_css():
    content = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in content
    assert "cdnjs.cloudflare.com" not in content


def test_frontend_entry_imports_local_fonts_and_icons():
    content = Path("frontend/src/main.js").read_text(encoding="utf-8")
    assert "@fontsource/bangers" in content
    assert "@fontsource/bebas-neue" in content
    assert "@fontsource/inter" in content
    assert "@fontsource/space-grotesk" in content
    assert "@fortawesome/fontawesome-free/css/all.css" in content


def _load_app(monkeypatch, serve_frontend: str | None):
    if serve_frontend is None:
        monkeypatch.delenv("SERVE_FRONTEND", raising=False)
    else:
        monkeypatch.setenv("SERVE_FRONTEND", serve_frontend)
    if "app.main" in sys.modules:
        module = reload(sys.modules["app.main"])
    else:
        import app.main as module
    return module.app


def test_frontend_served_only_in_dev(monkeypatch):
    app = _load_app(monkeypatch, "dev")
    with TestClient(app) as client:
        resp = client.get("/")
        # In dev mode, "/" serves built frontend if dist exists, otherwise returns a clear 500.
        assert resp.status_code in {200, 500}
        if resp.status_code == 500:
            assert "Frontend build not found" in resp.text

    app = _load_app(monkeypatch, "off")
    with TestClient(app) as client:
        resp = client.get("/")
        assert resp.status_code == 404
