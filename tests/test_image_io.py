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
