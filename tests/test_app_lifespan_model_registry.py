from pathlib import Path

from fastapi.testclient import TestClient


def test_lifespan_creates_model_registry():
    # Ensure required directories exist before importing app
    Path("data").mkdir(exist_ok=True)
    Path("output").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    Path("app/static").mkdir(parents=True, exist_ok=True)

    from app.main import app

    with TestClient(app):
        assert hasattr(app.state, "model_registry")
