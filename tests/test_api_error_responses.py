from pathlib import Path

from fastapi.testclient import TestClient

for name in ("data", "output", "static", "temp"):
    Path(name).mkdir(parents=True, exist_ok=True)

from app.main import app
from app.deps import get_pipeline


def test_http_exception_payload_includes_error_meta_and_request_id():
    client = TestClient(app)
    request_id = "test-http-exception-id"
    response = client.get(
        "/api/v1/manga/not-exists/chapters",
        headers={"X-Request-Id": request_id},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["detail"] == "Manga not found"
    assert payload["error"]["code"] == "HTTP_404"
    assert payload["error"]["request_id"] == request_id
    assert response.headers.get("x-request-id") == request_id


def test_validation_error_payload_is_structured():
    client = TestClient(app)
    response = client.post("/api/v1/translate/image", json={})

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert payload["error"]["message"] == "Request validation failed"
    assert isinstance(payload["detail"], list)
    assert payload["error"]["request_id"]
    assert response.headers.get("x-request-id") == payload["error"]["request_id"]


def test_unhandled_exception_returns_sanitized_500_payload(tmp_path):
    img_path = tmp_path / "input.png"
    img_path.write_bytes(b"img")

    class _BoomPipeline:
        async def process(self, context, status_callback=None):
            raise RuntimeError("boom")

    app.dependency_overrides[get_pipeline] = lambda: _BoomPipeline()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/v1/translate/image",
            json={"image_path": str(img_path)},
            headers={"X-Request-Id": "test-boom-500"},
        )
        assert response.status_code == 500
        payload = response.json()
        assert payload["detail"] == "Internal server error"
        assert payload["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert payload["error"]["request_id"] == "test-boom-500"
        assert response.headers.get("x-request-id") == "test-boom-500"
    finally:
        app.dependency_overrides = {}
