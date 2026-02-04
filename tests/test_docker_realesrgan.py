from pathlib import Path


def test_dockerfile_downloads_realesrgan_binary():
    content = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "realesrgan-ncnn-vulkan" in content


def test_docker_compose_sets_upscale_binary_path():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "UPSCALE_BINARY_PATH" in content
