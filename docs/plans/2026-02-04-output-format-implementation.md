# Output Format (WebP) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a global output format switch (WebP/PNG) and route all image outputs through a single save utility.

**Architecture:** Introduce `core/image_io.py` for save/format normalization; update all image writers to use it; update API output discovery to be extension-agnostic.

**Tech Stack:** Python, Pillow, OpenCV, pytest.

---

### Task 1: Add save utility tests

**Files:**
- Create: `tests/test_image_io.py`

**Step 1: Write failing tests**

```python
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
```

**Step 2: Run tests (expect fail)**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_image_io.py
```
Expected: FAIL (missing module/functions).

**Step 3: Commit**
```bash
git add tests/test_image_io.py
git commit -m "test: add image save utility tests"
```

---

### Task 2: Implement image IO utility

**Files:**
- Create: `core/image_io.py`

**Step 1: Minimal implementation**

```python
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

    # PNG
    if isinstance(image, Image.Image):
        image.save(out_path, format="PNG")
    else:
        cv2.imwrite(str(out_path), image)
    return str(out_path)
```

**Step 2: Run tests**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_image_io.py
```
Expected: PASS.

**Step 3: Commit**
```bash
git add core/image_io.py
git commit -m "feat: add image IO save utility"
```

---

### Task 3: Wire renderer + debug artifacts to save_image

**Files:**
- Modify: `core/renderer.py`
- Modify: `core/modules/renderer.py`
- Modify: `core/debug_artifacts.py`

**Step 1: Update renderer save**
- Replace `image.save(output_path)` with `save_image(image, output_path, purpose="final")`
- Ensure returned path is propagated to `context.output_path`.

**Step 2: Update debug artifacts**
- Replace `img.save(out_path)` / `Image.open(...).save(...)` calls with `save_image(..., purpose="intermediate")`

**Step 3: Run focused tests**
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_renderer_font_size.py
```
Expected: PASS.

**Step 4: Commit**
```bash
git add core/renderer.py core/modules/renderer.py core/debug_artifacts.py
git commit -m "feat: save renderer and debug outputs via image IO"
```

---

### Task 4: Wire inpainter + text detector + image processor

**Files:**
- Modify: `core/modules/inpainter.py`
- Modify: `core/vision/inpainter.py`
- Modify: `core/vision/text_detector.py`
- Modify: `core/vision/image_processor.py`

**Step 1: Replace cv2.imwrite/PIL save for masks/inpainted**
- Use `save_image(..., purpose="intermediate")` for masks and inpainted outputs.
- Ensure returned path is used where needed.

**Step 2: Run focused tests**
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_inpainter_module.py tests/test_inpaint_gap_fill.py tests/test_debug_artifacts.py
```
Expected: PASS.

**Step 3: Commit**
```bash
git add core/modules/inpainter.py core/vision/inpainter.py core/vision/text_detector.py core/vision/image_processor.py
git commit -m "feat: save inpaint artifacts via image IO"
```

---

### Task 5: Wire upscaler outputs

**Files:**
- Modify: `core/modules/upscaler.py`

**Step 1: Pytorch backend**
- Replace `cv2.imwrite` with `save_image(..., purpose="intermediate")`
- Ensure temp path and final path use normalized suffix (tmp should match output suffix)

**Step 2: NCNN backend**
- Ensure tmp path uses normalized suffix (use `save_image` for final rename path if needed)

**Step 3: Run focused tests**
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_module.py
```
Expected: PASS.

**Step 4: Commit**
```bash
git add core/modules/upscaler.py
git commit -m "feat: save upscaler outputs via image IO"
```

---

### Task 6: Output discovery + routes

**Files:**
- Modify: `app/routes/manga.py`
- Modify: `app/routes/translate.py`
- Modify: `app/services/page_status.py`

**Step 1: Replace extension‑specific lookups**
- Use `glob(f\"{stem}.*\")` to find translated outputs.
- Prefer `.webp` if both exist; otherwise most recent.

**Step 2: Tests**
- Add test in `tests/test_page_status.py` to ensure webp is detected.

**Step 3: Run tests**
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_page_status.py
```
Expected: PASS.

**Step 4: Commit**
```bash
git add app/routes/manga.py app/routes/translate.py app/services/page_status.py tests/test_page_status.py
git commit -m "feat: discover translated outputs by glob"
```

---

### Task 7: Docs + env example

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Step 1: Add config docs**
```
OUTPUT_FORMAT=webp
WEBP_QUALITY_FINAL=90
WEBP_LOSSLESS_INTERMEDIATE=1
```

**Step 2: Commit**
```bash
git add README.md .env.example
git commit -m "docs: add output format config"
```

