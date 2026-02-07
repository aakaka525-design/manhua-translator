from pathlib import Path


def test_docker_compose_sets_ncnn_model_dir():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "UPSCALE_NCNN_MODEL_DIR" in compose


def test_docker_compose_uses_container_specific_upscale_paths():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "UPSCALE_BINARY_PATH_DOCKER" in compose
    assert "UPSCALE_NCNN_MODEL_DIR_DOCKER" in compose


def test_docker_compose_persists_paddleocr_cache_dir():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "/root/.paddleocr" in compose


def test_dockerfile_includes_vulkan_libs():
    dockerfile = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "libvulkan1" in dockerfile
    assert "mesa-vulkan-drivers" in dockerfile


def test_docker_cpu_requirements_include_google_genai():
    reqs = Path("docker/requirements-docker-cpu.txt").read_text(encoding="utf-8")
    assert "google-genai" in reqs


def test_docker_cpu_requirements_pin_ocr_runtime_versions():
    reqs = Path("docker/requirements-docker-cpu.txt").read_text(encoding="utf-8")
    assert "paddleocr==3.3.3" in reqs
    assert "paddlepaddle==3.3.0" in reqs
    assert "paddlex==3.3.13" in reqs


def test_dockerfile_installs_torch_with_lama():
    dockerfile = Path("docker/Dockerfile.api").read_text(encoding="utf-8")
    assert "simple-lama-inpainting==0.1.2" in dockerfile
    assert "pip install torch torchvision" in dockerfile
