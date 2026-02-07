from pathlib import Path

from fastapi.testclient import TestClient

for name in ("data", "output", "static", "temp"):
    Path(name).mkdir(parents=True, exist_ok=True)

from app.main import app
import app.routes.scraper as scraper_routes
from scraper.implementations.generic_playwright import CloudflareChallengeError


class _SearchChallengeEngine:
    async def search(self, keyword):
        raise CloudflareChallengeError("需要通过 Cloudflare 验证")


def test_scraper_search_returns_layered_auth_error(monkeypatch):
    monkeypatch.setattr(
        scraper_routes,
        "_build_engine",
        lambda request, output_root: (_SearchChallengeEngine(), request.base_url),
    )
    client = TestClient(app)
    response = client.post(
        "/api/v1/scraper/search",
        json={"base_url": "https://toongod.org", "keyword": "abc"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["code"] == "SCRAPER_AUTH_CHALLENGE"
    assert "Cloudflare" in payload["detail"]["message"]
    assert payload["error"]["code"] == "HTTP_403"


def test_upload_state_invalid_file_type_has_specific_error_code():
    client = TestClient(app)
    response = client.post(
        "/api/v1/scraper/upload-state",
        data={"base_url": "https://toongod.org"},
        files={"file": ("state.txt", b"{}", "text/plain")},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["detail"]["code"] == "SCRAPER_STATE_FILE_TYPE_INVALID"
    assert payload["error"]["code"] == "HTTP_400"


def test_scraper_task_not_found_has_queue_error_code():
    client = TestClient(app)
    response = client.get("/api/v1/scraper/task/not-found")

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"]["code"] == "SCRAPER_TASK_NOT_FOUND"
    assert payload["error"]["code"] == "HTTP_404"
