from fastapi.testclient import TestClient


def test_settings_upscale_update():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/settings/upscale",
            json={"model": "realesr-animevideov3-x4", "scale": 4, "enabled": False},
        )
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/settings")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["upscale_model"] == "realesr-animevideov3-x4"
        assert data["upscale_scale"] == 4
        assert data["upscale_enable"] is False


def test_settings_upscale_validation():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/settings/upscale",
            json={"model": "bad-model", "scale": 4},
        )
        assert resp.status_code == 422

        resp = client.post(
            "/api/v1/settings/upscale",
            json={"model": "realesr-animevideov3-x4", "scale": 3},
        )
        assert resp.status_code == 422


def test_settings_upscale_model_scale_pairing():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/settings/upscale",
            json={"model": "realesr-animevideov3-x2", "scale": 2},
        )
        assert resp.status_code == 200

        resp = client.post(
            "/api/v1/settings/upscale",
            json={"model": "realesr-animevideov3-x2", "scale": 4},
        )
        assert resp.status_code == 422
