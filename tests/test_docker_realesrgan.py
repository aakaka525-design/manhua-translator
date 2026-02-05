from pathlib import Path


def test_dockerfile_downloads_realesrgan_binary():
    content = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "realesrgan-ncnn-vulkan" in content


def test_dockerfile_uses_latest_ncnn_zip():
    content = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "ARG REALESRGAN_VERSION=0.2.5.0" in content
    assert (
        "Real-ESRGAN/releases/download/v${REALESRGAN_VERSION}/"
        "realesrgan-ncnn-vulkan-20220424-ubuntu.zip"
        in content
    )


def test_docker_compose_sets_upscale_binary_path():
    content = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "UPSCALE_BINARY_PATH" in content
