import os

from fastapi.testclient import TestClient

from app.main import app


def test_model_override_does_not_touch_env(monkeypatch):
    monkeypatch.delenv("PPIO_MODEL", raising=False)

    client = TestClient(app)
    resp = client.post("/api/v1/settings/model", json={"model": "foo"})
    assert resp.status_code == 200

    assert os.getenv("PPIO_MODEL") is None
