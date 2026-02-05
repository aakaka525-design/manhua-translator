# Upscale Stripe Segmentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add stripe-based upscale for tall images to speed up PyTorch Real-ESRGAN, with clear logs and safe stitching.

**Architecture:** Split tall images into overlapping horizontal stripes, upscale each stripe, trim overlaps, and concatenate to reconstruct output. Only active when `UPSCALE_STRIPE_ENABLE=1` and `H > UPSCALE_STRIPE_THRESHOLD`.

**Tech Stack:** Python, NumPy, OpenCV, RealESRGAN (PyTorch), pytest.

---

### Task 1: Add unit tests for stripe helpers

**Files:**
- Create: `tests/test_upscaler_stripes.py`

**Step 1: Write the failing tests**

```python
import numpy as np
import pytest

from core.modules import upscaler


def test_compute_stripes_returns_full_when_below_threshold():
    stripes = upscaler.compute_stripes(height=1000, threshold=4000, stripe_height=2000, overlap=64)
    assert stripes == [(0, 1000)]


def test_compute_stripes_merges_small_tail():
    # height=4100 with stripe=2000, overlap=64 leaves tail < overlap
    stripes = upscaler.compute_stripes(height=4100, threshold=4000, stripe_height=2000, overlap=64)
    assert stripes[-1][1] == 4100
    # ensure only 2 stripes, tail merged
    assert len(stripes) == 2


def test_compute_stripes_rejects_bad_config():
    with pytest.raises(ValueError):
        upscaler.compute_stripes(height=5000, threshold=4000, stripe_height=64, overlap=64)


def test_crop_and_merge_preserves_total_height():
    # three stripes with overlap 2 at scale 2 => overlap_px=4
    stripes = [
        np.zeros((10, 4, 3), dtype=np.uint8),
        np.zeros((10, 4, 3), dtype=np.uint8),
        np.zeros((10, 4, 3), dtype=np.uint8),
    ]
    merged = upscaler.crop_and_merge(stripes, overlap_px=4, scale=2)
    # first keeps 6, middle keeps 2, last keeps 6 => 14 total
    assert merged.shape[0] == 14
```

**Step 2: Run tests to verify they fail**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_stripes.py
```
Expected: FAIL with `AttributeError` or `NameError` for missing `compute_stripes` / `crop_and_merge`.

**Step 3: Commit**

```bash
git add tests/test_upscaler_stripes.py
git commit -m "test: add stripe helper tests"
```

---

### Task 2: Implement stripe helpers in upscaler

**Files:**
- Modify: `core/modules/upscaler.py`

**Step 1: Implement helpers**

```python
def compute_stripes(height: int, threshold: int, stripe_height: int, overlap: int) -> list[tuple[int, int]]:
    if height <= threshold:
        return [(0, height)]
    if stripe_height <= overlap:
        raise ValueError("stripe_height must be greater than overlap")
    stripes = []
    start = 0
    while start < height:
        end = min(start + stripe_height, height)
        remaining = height - end
        if remaining > 0 and remaining < overlap:
            end = height
        stripes.append((start, end))
        if end >= height:
            break
        start = end - overlap
    return stripes


def crop_and_merge(stripes: list, overlap_px: int, scale: int):
    import numpy as np
    if not stripes:
        raise ValueError("no stripes to merge")
    if len(stripes) == 1 or overlap_px <= 0:
        return np.concatenate(stripes, axis=0) if len(stripes) > 1 else stripes[0]
    trimmed = []
    for idx, stripe in enumerate(stripes):
        if stripe.shape[0] <= overlap_px:
            raise ValueError("stripe height too small for overlap")
        if idx == 0:
            trimmed.append(stripe[:-overlap_px])
        elif idx == len(stripes) - 1:
            trimmed.append(stripe[overlap_px:])
        else:
            if stripe.shape[0] <= 2 * overlap_px:
                raise ValueError("stripe height too small for double overlap")
            trimmed.append(stripe[overlap_px:-overlap_px])
    return np.concatenate(trimmed, axis=0)
```

**Step 2: Run tests to verify they pass**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_stripes.py
```
Expected: PASS.

**Step 3: Commit**

```bash
git add core/modules/upscaler.py
git commit -m "feat: add stripe helpers for upscaler"
```

---

### Task 3: Wire stripe mode into PyTorch upscale path

**Files:**
- Modify: `core/modules/upscaler.py`

**Step 1: Add stripe env defaults**
```python
DEFAULT_STRIPE_ENABLE = "0"
DEFAULT_STRIPE_THRESHOLD = 4000
DEFAULT_STRIPE_HEIGHT = 2000
DEFAULT_STRIPE_OVERLAP = 64
```

**Step 2: Add integration in `_run_pytorch`**

```python
stripe_enable = os.getenv("UPSCALE_STRIPE_ENABLE", DEFAULT_STRIPE_ENABLE) == "1"
threshold = int(os.getenv("UPSCALE_STRIPE_THRESHOLD", str(DEFAULT_STRIPE_THRESHOLD)))
stripe_height = int(os.getenv("UPSCALE_STRIPE_HEIGHT", str(DEFAULT_STRIPE_HEIGHT)))
overlap = int(os.getenv("UPSCALE_STRIPE_OVERLAP", str(DEFAULT_STRIPE_OVERLAP)))

if stripe_enable and image.shape[0] > threshold:
    stripes = compute_stripes(image.shape[0], threshold, stripe_height, overlap)
    logger.info("stripe: segments=%d h=%d threshold=%d overlap=%d", len(stripes), image.shape[0], threshold, overlap)
    outputs = []
    overlap_px = int(overlap * scale)
    for i, (start, end) in enumerate(stripes):
        stripe = image[start:end, :, :]
        start_t = time.perf_counter()
        try:
            out, _ = upsampler.enhance(stripe, outscale=scale)
        except Exception as exc:
            logger.error("stripe[%d] failed: input_size=%sx%s error=%s", i, stripe.shape[1], stripe.shape[0], exc)
            raise RuntimeError(f"Stripe {i} upscale failed") from exc
        elapsed = (time.perf_counter() - start_t) * 1000
        logger.debug("stripe[%d]: input_h=%d output_h=%d ms=%.0f", i, stripe.shape[0], out.shape[0], elapsed)
        outputs.append(out)
    output = crop_and_merge(outputs, overlap_px=overlap_px, scale=scale)
else:
    output, _ = upsampler.enhance(image, outscale=scale)
```

**Step 3: Run tests**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_module.py tests/test_upscaler_stripes.py
```
Expected: PASS.

**Step 4: Commit**

```bash
git add core/modules/upscaler.py
git commit -m "feat: add stripe-based pytorch upscale"
```

---

### Task 4: Document new env settings

**Files:**
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/test_env_example_upscale.py`

**Step 1: Update `.env.example`**
```env
UPSCALE_STRIPE_ENABLE=0
UPSCALE_STRIPE_THRESHOLD=4000
UPSCALE_STRIPE_HEIGHT=2000
UPSCALE_STRIPE_OVERLAP=64
```

**Step 2: Update README section**
Add description and when stripe mode triggers.

**Step 3: Update env test**
```python
assert "UPSCALE_STRIPE_ENABLE" in content
assert "UPSCALE_STRIPE_THRESHOLD" in content
assert "UPSCALE_STRIPE_HEIGHT" in content
assert "UPSCALE_STRIPE_OVERLAP" in content
```

**Step 4: Run tests**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_env_example_upscale.py
```
Expected: PASS.

**Step 5: Commit**
```bash
git add .env.example README.md tests/test_env_example_upscale.py
git commit -m "docs: add stripe upscale env settings"
```

---

### Task 5: Manual verification (optional)

**Run:**
```bash
PYTHONPATH=/Users/xa/Desktop/projiect/manhua/.worktrees/upscale-realesrgan \
UPSCALE_ENABLE=1 UPSCALE_BACKEND=pytorch UPSCALE_DEVICE=mps \
UPSCALE_MODEL_PATH=/Users/xa/Desktop/projiect/manhua/.worktrees/upscale-realesrgan/tools/bin/RealESRGAN_x4plus.pth \
UPSCALE_STRIPE_ENABLE=1 UPSCALE_STRIPE_THRESHOLD=4000 \
UPSCALE_STRIPE_HEIGHT=2000 UPSCALE_STRIPE_OVERLAP=64 \
UPSCALE_TILE=256 UPSCALE_SCALE=2 UPSCALE_TIMEOUT=900 \
/Users/xa/Desktop/projiect/manhua/.venv/bin/python scripts/upscale_eval.py \
/Users/xa/Desktop/projiect/manhua/data/raw/sexy-woman/chapter-1/1.jpg --lang korean --format json
```

Expected: log shows stripe segments and per-stripe timings; report generated.

