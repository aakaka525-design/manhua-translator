import json
import os
from pathlib import Path

import numpy as np
from PIL import Image

from core.image_io import save_image


def test_save_image_rewrites_suffix_to_webp(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    img = Image.new("RGB", (4, 4), "white")
    path = tmp_path / "out.png"
    saved = save_image(img, str(path), purpose="final")
    assert saved.endswith(".webp")
    assert Path(saved).exists()


def test_save_image_png_passthrough(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "png")
    img = Image.new("RGB", (4, 4), "white")
    path = tmp_path / "out.png"
    saved = save_image(img, str(path), purpose="final")
    assert saved.endswith(".png")
    assert Path(saved).exists()


def test_save_image_supports_ndarray(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    path = tmp_path / "out.jpg"
    saved = save_image(arr, str(path), purpose="intermediate")
    assert saved.endswith(".webp")
    assert Path(saved).exists()


def test_save_image_ndarray_webp_uses_pil(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    path = tmp_path / "out.jpg"

    import core.image_io as image_io

    def _boom(*args, **kwargs):
        raise AssertionError("cv2.imwrite should not be called for webp ndarray")

    monkeypatch.setattr(image_io.cv2, "imwrite", _boom)
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith(".webp")
    assert Path(saved).exists()


def test_save_image_webp_too_large_falls_back_to_png(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    arr = np.zeros((10, 20000, 3), dtype=np.uint8)
    path = tmp_path / "out.jpg"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith(".png")
    assert Path(saved).exists()


def test_save_image_webp_oversize_slices(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith("_slices.json")
    assert (tmp_path / "out_slices").exists()


def test_save_image_webp_slice_failure_falls_back_png(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    import core.image_io as image_io

    def _boom(*args, **kwargs):
        raise OSError("fail")

    monkeypatch.setattr(image_io.Image.Image, "save", _boom, raising=False)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith(".png")


def test_save_image_webp_oversize_respects_overlap_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    monkeypatch.setenv("WEBP_SLICE_OVERLAP", "10")
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith("_slices.json")
    data = json.loads(Path(saved).read_text())
    assert data["overlap"] == 10


def test_save_image_webp_slices_lossless_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    monkeypatch.setenv("WEBP_SLICES_LOSSLESS", "1")
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)

    import core.image_io as image_io

    calls = []

    def _spy(self, fp, format=None, **kwargs):
        Path(fp).write_bytes(b"")
        calls.append((format, kwargs))

    monkeypatch.setattr(image_io.Image.Image, "save", _spy, raising=False)

    saved = save_image(arr, str(tmp_path / "out.png"), purpose="final")
    assert saved.endswith("_slices.json")
    assert calls, "expected at least one slice save"
    fmt, kwargs = calls[0]
    assert fmt == "WEBP"
    assert kwargs.get("lossless") is True
    assert "quality" not in kwargs
