import os
from pathlib import Path
from typing import Literal, Union

import cv2
import numpy as np
from PIL import Image


def _output_format() -> str:
    fmt = os.getenv("OUTPUT_FORMAT", "webp").strip().lower()
    if fmt not in {"webp", "png"}:
        raise ValueError(f"Unsupported OUTPUT_FORMAT: {fmt}")
    return fmt


def _normalize_suffix(path: Path) -> Path:
    fmt = _output_format()
    return path.with_suffix(".webp" if fmt == "webp" else ".png")


def compute_webp_slices(height: int, slice_height: int, overlap: int) -> list[tuple[int, int]]:
    if height <= 16383:
        return [(0, height)]
    if slice_height <= overlap:
        raise ValueError("slice_height must be greater than overlap")
    slices: list[tuple[int, int]] = []
    stride = slice_height - overlap
    start = 0
    while start < height:
        end = min(start + slice_height, height)
        remaining = height - end
        if remaining > 0 and remaining <= overlap:
            end = height
            slices.append((start, end))
            break
        slices.append((start, end))
        if end >= height:
            break
        start = start + stride
    return slices


def save_image(
    image: Union[Image.Image, np.ndarray],
    path: str,
    *,
    purpose: Literal["final", "intermediate"] = "intermediate",
) -> str:
    out_path = _normalize_suffix(Path(path))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fmt = _output_format()
    if fmt == "webp":
        if isinstance(image, Image.Image):
            width, height = image.size
        else:
            height, width = image.shape[:2]
        if width > 16383 or height > 16383:
            fmt = "png"
            out_path = out_path.with_suffix(".png")
    if fmt == "webp":
        if purpose == "final":
            quality = int(os.getenv("WEBP_QUALITY_FINAL", "90"))
            if isinstance(image, Image.Image):
                image.save(out_path, format="WEBP", quality=quality)
            else:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                Image.fromarray(rgb).save(out_path, format="WEBP", quality=quality)
        else:
            if isinstance(image, Image.Image):
                image.save(out_path, format="WEBP", lossless=True)
            else:
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                Image.fromarray(rgb).save(out_path, format="WEBP", lossless=True)
        return str(out_path)

    if isinstance(image, Image.Image):
        image.save(out_path, format="PNG")
    else:
        cv2.imwrite(str(out_path), image)
    return str(out_path)
