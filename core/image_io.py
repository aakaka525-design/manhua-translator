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
        if purpose == "final":
            quality = int(os.getenv("WEBP_QUALITY_FINAL", "90"))
            if isinstance(image, Image.Image):
                image.save(out_path, format="WEBP", quality=quality)
            else:
                cv2.imwrite(str(out_path), image, [cv2.IMWRITE_WEBP_QUALITY, quality])
        else:
            if isinstance(image, Image.Image):
                image.save(out_path, format="WEBP", lossless=True)
            else:
                cv2.imwrite(str(out_path), image, [cv2.IMWRITE_WEBP_QUALITY, 100])
        return str(out_path)

    if isinstance(image, Image.Image):
        image.save(out_path, format="PNG")
    else:
        cv2.imwrite(str(out_path), image)
    return str(out_path)
