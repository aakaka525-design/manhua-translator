from pathlib import Path


def test_setup_local_script_exists():
    script = Path("scripts/setup_local.sh")
    assert script.exists()


def test_gitignore_includes_tools_bin():
    content = Path(".gitignore").read_text(encoding="utf-8")
    assert "/tools/bin/" in content


def test_setup_local_script_uses_latest_ncnn_urls():
    content = Path("scripts/setup_local.sh").read_text(encoding="utf-8")
    assert "v0.2.5.0" in content
    assert "realesrgan-ncnn-vulkan-20220424-macos.zip" in content
    assert "realesrgan-ncnn-vulkan-20220424-ubuntu.zip" in content
    assert "Real-ESRGAN/releases/download" in content


def test_setup_local_script_filters_macosx_artifacts():
    content = Path("scripts/setup_local.sh").read_text(encoding="utf-8")
    assert "__MACOSX" in content
    assert "realesrgan-ncnn-vulkan" in content


def test_setup_local_script_copies_extracted_root():
    content = Path("scripts/setup_local.sh").read_text(encoding="utf-8")
    assert "SRC_ROOT" in content
    assert "cp -R \"$SRC_ROOT\"/* \"$BIN_DIR\"/" in content


def test_setup_local_script_sources_env():
    content = Path("scripts/setup_local.sh").read_text(encoding="utf-8")
    assert "source \"$ROOT_DIR/.env\"" in content
    assert "set -a" in content


def test_setup_local_script_handles_root_files():
    content = Path("scripts/setup_local.sh").read_text(encoding="utf-8")
    assert "TOP_LEVEL_ENTRIES" in content
    assert "SRC_ROOT=\"$TMP_DIR/extract\"" in content
