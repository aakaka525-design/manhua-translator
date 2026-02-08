from pathlib import Path

from fastapi.testclient import TestClient


def test_system_runtime_endpoint_has_expected_sections():
    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    Path("app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/system/runtime")
        assert resp.status_code == 200
        payload = resp.json()
        assert "versions" in payload
        assert "settings" in payload
        assert "model_registry" in payload
        assert "paths" in payload
        assert "ocr" in payload["settings"]
