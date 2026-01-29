from pathlib import Path

from fastapi.testclient import TestClient


def test_system_models_endpoint():
    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    Path("app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app

    with TestClient(app) as client:
        resp = client.get("/api/v1/system/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "ppocr_det" in data
