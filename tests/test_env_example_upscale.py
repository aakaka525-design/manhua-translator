from pathlib import Path


def test_env_example_includes_upscale_settings():
    content = Path(".env.example").read_text(encoding="utf-8")
    assert "UPSCALE_ENABLE" in content
    assert "UPSCALE_BACKEND" in content
    assert "UPSCALE_DEVICE" in content
    assert "UPSCALE_BINARY_PATH" in content
    assert "UPSCALE_MODEL_PATH" in content
    assert "UPSCALE_MODEL" in content
    assert "UPSCALE_SCALE" in content
    assert "UPSCALE_TIMEOUT" in content
    assert "UPSCALE_TILE" in content
