from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_settings_language_update_updates_response(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_text("SOURCE_LANGUAGE=en\nTARGET_LANGUAGE=zh\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_path))

    client = TestClient(app)

    resp = client.post(
        "/api/v1/settings/language",
        json={
            "source_language": "ja",
            "target_language": "zh-CN",
        },
    )
    assert resp.status_code == 200

    settings = client.get("/api/v1/settings").json()
    assert settings["source_language"] == "ja"
    assert settings["target_language"] == "zh-CN"

    content = env_path.read_text(encoding="utf-8")
    assert "SOURCE_LANGUAGE=ja" in content
    assert "TARGET_LANGUAGE=zh-CN" in content
