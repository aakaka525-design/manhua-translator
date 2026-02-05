import json
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


def _webp_slice_overlap() -> int:
    return int(os.getenv("WEBP_SLICE_OVERLAP", "10"))


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


def _save_webp_slices(
    image: Union[Image.Image, np.ndarray],
    out_path: Path,
    *,
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

    slices = compute_webp_slices(height, slice_height, overlap)
    slices_dir = out_path.parent / f"{out_path.stem}_slices"
    slices_dir.mkdir(parents=True, exist_ok=True)

    entries = []
    for idx, (start, end) in enumerate(slices):
        filename = f"slice_{idx:03d}.webp"
        crop = pil.crop((0, start, width, end))
        crop.save(slices_dir / filename, format="WEBP", quality=int(os.getenv("WEBP_QUALITY_FINAL", "90")))
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
        if height > 16383:
            if purpose == "final" and width <= 16383:
                try:
                    return _save_webp_slices(image, out_path, overlap=_webp_slice_overlap())
                except Exception:
                    out_path = out_path.with_suffix(".png")
                    if isinstance(image, Image.Image):
                        image.save(out_path, format="PNG")
                    else:
                        cv2.imwrite(str(out_path), image)
                    return str(out_path)
            fmt = "png"
            out_path = out_path.with_suffix(".png")
        elif width > 16383:
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
