from pathlib import Path


def test_prebuilt_compose_references_ghcr_images():
    content = Path("docker-compose.prebuilt.yml").read_text(encoding="utf-8")
    assert "ghcr.io/aakaka525-design/manhua-translator-api" in content
    assert "ghcr.io/aakaka525-design/manhua-translator-web" in content


def test_start_script_uses_prebuilt_compose():
    content = Path("scripts/start_docker.sh").read_text(encoding="utf-8")
    assert "docker-compose.prebuilt.yml" in content
    assert "docker compose" in content


def test_workflow_publishes_ghcr_images():
    content = Path(".github/workflows/docker-publish.yml").read_text(encoding="utf-8")
    assert "ghcr.io/aakaka525-design/manhua-translator-api" in content
    assert "ghcr.io/aakaka525-design/manhua-translator-web" in content
