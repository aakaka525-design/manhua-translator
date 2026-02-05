from pathlib import Path


def test_docker_compose_sets_ncnn_model_dir():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "UPSCALE_NCNN_MODEL_DIR" in compose


def test_dockerfile_includes_vulkan_libs():
    dockerfile = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "libvulkan1" in dockerfile
    assert "mesa-vulkan-drivers" in dockerfile
