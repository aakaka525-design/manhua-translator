import json
import os
import shutil
from pathlib import Path
from typing import Literal, Union

import cv2
import numpy as np
from PIL import Image


WEBP_MAX_DIM = 16383


def _output_format() -> str:
    fmt = os.getenv("OUTPUT_FORMAT", "webp").strip().lower()
    if fmt not in {"webp", "png"}:
        raise ValueError(f"Unsupported OUTPUT_FORMAT: {fmt}")
    return fmt


def _normalize_suffix(path: Path) -> Path:
    fmt = _output_format()
    return path.with_suffix(".webp" if fmt == "webp" else ".png")


def _webp_slice_overlap() -> int:
    return int(os.getenv("WEBP_SLICE_OVERLAP", "10"))


def _webp_slices_lossless() -> bool:
    return os.getenv("WEBP_SLICES_LOSSLESS", "0") == "1"


def _webp_slice_threshold() -> int:
    """
    Height threshold for writing final WebP outputs as *_slices/ + *_slices.json.

    Default matches WebP's max dimension (16383). You can lower this (e.g. 8192/4096)
    to avoid mobile devices failing to decode/render very tall images.
    """
    raw = os.getenv("WEBP_SLICE_THRESHOLD", str(WEBP_MAX_DIM)).strip()
    try:
        value = int(raw)
    except ValueError:
        value = WEBP_MAX_DIM
    if value <= 0:
        value = WEBP_MAX_DIM
    return min(value, WEBP_MAX_DIM)


def _webp_slice_height() -> int:
    """Target height for each slice file (clamped to WEBP_SLICE_THRESHOLD / WEBP_MAX_DIM)."""
    raw = os.getenv("WEBP_SLICE_HEIGHT", "16000").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 16000
    if value <= 0:
        value = 16000
    return min(value, WEBP_MAX_DIM)


def compute_webp_slices(
    height: int, slice_height: int, overlap: int, *, threshold: int = WEBP_MAX_DIM
) -> list[tuple[int, int]]:
    if height <= threshold:
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


def _save_webp_slices(
    image: Union[Image.Image, np.ndarray],
    out_path: Path,
    *,
    threshold: int = WEBP_MAX_DIM,
    slice_height: int = 16000,
    overlap: int = 32,
) -> str:
    if isinstance(image, Image.Image):
        pil = image
        width, height = pil.size
    else:
        height, width = image.shape[:2]
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)

    slices = compute_webp_slices(height, slice_height, overlap, threshold=threshold)
    slices_dir = out_path.parent / f"{out_path.stem}_slices"
    if slices_dir.exists():
        shutil.rmtree(slices_dir)
    slices_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for idx, (start, end) in enumerate(slices):
        filename = f"slice_{idx:03d}.webp"
        crop = pil.crop((0, start, width, end))
        path = slices_dir / filename
        if _webp_slices_lossless():
            crop.save(path, format="WEBP", lossless=True)
        else:
            crop.save(path, format="WEBP", quality=int(os.getenv("WEBP_QUALITY_FINAL", "90")))
        entries.append({"file": filename, "y": start, "height": end - start})

    index_path = out_path.parent / f"{out_path.stem}_slices.json"
    index_path.write_text(
        json.dumps(
            {
                "version": 1,
                "original_width": width,
                "original_height": height,
                "slice_height": slice_height,
                "overlap": overlap,
                "slices": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    # Avoid leaving a stale single-file artifact that can cause manual inspection confusion.
    if out_path.exists():
        out_path.unlink()
    return str(index_path)


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

        # Optional slicing for final WebP outputs. This is also required for heights > WEBP_MAX_DIM.
        if purpose == "final" and width <= WEBP_MAX_DIM:
            slice_threshold = _webp_slice_threshold()
            if height > slice_threshold:
                try:
                    overlap = _webp_slice_overlap()
                    slice_height = min(_webp_slice_height(), slice_threshold)
                    # Worst case the last slice can be up to (slice_height + overlap) tall.
                    if slice_height + overlap > slice_threshold:
                        slice_height = max(overlap + 1, slice_threshold - overlap)
                    return _save_webp_slices(
                        image,
                        out_path,
                        threshold=slice_threshold,
                        slice_height=slice_height,
                        overlap=overlap,
                    )
                except Exception:
                    out_path = out_path.with_suffix(".png")
                    if isinstance(image, Image.Image):
                        image.save(out_path, format="PNG")
                    else:
                        cv2.imwrite(str(out_path), image)
                    return str(out_path)

        if height > WEBP_MAX_DIM:
            fmt = "png"
            out_path = out_path.with_suffix(".png")
        elif width > WEBP_MAX_DIM:
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
