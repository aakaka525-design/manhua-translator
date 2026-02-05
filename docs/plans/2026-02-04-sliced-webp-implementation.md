# Sliced WebP Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan.

**Goal:** Automatically slice oversized WebP outputs into multiple WebP files plus JSON index when height exceeds 16383px, with PNG fallback on failure.

**Architecture:** Extend `core.image_io.save_image` with a slice path that writes `<stem>_slices/` and `<stem>_slices.json` when `OUTPUT_FORMAT=webp` and height exceeds limit. Ensure callers receive the index path and downstream lookup handles it.

**Tech Stack:** Python, Pillow, NumPy, existing image IO helpers.

---

### Task 1: Add slice math helpers + unit tests

**Files:**
- Create: `tests/test_image_slices.py`
- Modify: `core/image_io.py`

**Step 1: Write the failing test**

Create `tests/test_image_slices.py`:
```python
import pytest
from core.image_io import compute_webp_slices


@pytest.mark.parametrize("height,expected_slices", [
    (16383, 1),
    (16384, 2),
    (32000, 2),
    (62012, 4),
])
def test_slice_count(height, expected_slices):
    slices = compute_webp_slices(height, slice_height=16000, overlap=32)
    assert len(slices) == expected_slices


def test_slice_positions():
    slices = compute_webp_slices(62012, slice_height=16000, overlap=32)
    assert slices[0] == (0, 16000)
    assert slices[1][0] == 15968
    assert slices[-1][1] == 62012
```

**Step 2: Run test to verify it fails**
Run: `pytest -q tests/test_image_slices.py::test_slice_count`
Expected: FAIL (compute_webp_slices missing)

**Step 3: Write minimal implementation**
Add to `core/image_io.py`:
```python
def compute_webp_slices(height: int, slice_height: int, overlap: int) -> list[tuple[int, int]]:
    if height <= 16383:
        return [(0, height)]
    if slice_height <= overlap:
        raise ValueError("slice_height must be greater than overlap")
    slices = []
    stride = slice_height - overlap
    start = 0
    while start < height:
        end = min(start + slice_height, height)
        slices.append((start, end))
        if end >= height:
            break
        start = start + stride
    return slices
```

**Step 4: Run test to verify it passes**
Run: `pytest -q tests/test_image_slices.py`
Expected: PASS

**Step 5: Commit**
```bash
git add core/image_io.py tests/test_image_slices.py
git commit -m "test: add webp slice math"
```

---

### Task 2: Implement sliced WebP writer + index JSON

**Files:**
- Modify: `core/image_io.py`
- Test: `tests/test_image_io.py`

**Step 1: Write failing test**
Add to `tests/test_image_io.py`:
```python
def test_save_image_webp_oversize_slices(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    import numpy as np
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith("_slices.json")
    assert (tmp_path / "out_slices").exists()
```

**Step 2: Run test to verify it fails**
Run: `pytest -q tests/test_image_io.py::test_save_image_webp_oversize_slices`
Expected: FAIL

**Step 3: Implement sliced write**
Extend `save_image`:
- On WebP and height > 16383: call `compute_webp_slices`.
- Create `<stem>_slices/` dir.
- Write each slice via PIL (RGB) to `slice_XXX.webp`.
- Write JSON index `<stem>_slices.json` with fields:
  - version, original_width, original_height, slice_height, overlap, slices[] (file, y, height)
- Return index path.

**Step 4: Run test to verify it passes**
Run: `pytest -q tests/test_image_io.py::test_save_image_webp_oversize_slices`
Expected: PASS

**Step 5: Commit**
```bash
git add core/image_io.py tests/test_image_io.py
git commit -m "feat: slice oversized webp outputs"
```

---

### Task 3: Fallback to PNG on slice failure

**Files:**
- Modify: `core/image_io.py`
- Test: `tests/test_image_io.py`

**Step 1: Write failing test**
Add to `tests/test_image_io.py`:
```python
def test_save_image_webp_slice_failure_falls_back_png(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    import numpy as np
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    import core.image_io as image_io

    def _boom(*args, **kwargs):
        raise OSError("fail")

    monkeypatch.setattr(image_io.Image.Image, "save", _boom, raising=False)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith(".png")
```

**Step 2: Run test to verify it fails**
Run: `pytest -q tests/test_image_io.py::test_save_image_webp_slice_failure_falls_back_png`
Expected: FAIL

**Step 3: Implement fallback**
Wrap slice writing in try/except:
- On any exception, log and write PNG single image (using existing PNG path).
- Return `.png` path.

**Step 4: Run test to verify it passes**
Run: `pytest -q tests/test_image_io.py::test_save_image_webp_slice_failure_falls_back_png`
Expected: PASS

**Step 5: Commit**
```bash
git add core/image_io.py tests/test_image_io.py
git commit -m "feat: fallback to png on slice failure"
```

---

### Task 4: Update output discovery to recognize slice index

**Files:**
- Modify: `app/services/page_status.py`
- Modify: `app/routes/manga.py`
- Modify: `app/routes/translate.py`
- Test: `tests/test_page_status.py`

**Step 1: Write failing test**
Add to `tests/test_page_status.py`:
```python
def test_find_translated_file_prefers_slices(tmp_path):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "page_slices").mkdir()
    (out_dir / "page_slices.json").write_text("{}");
    from app.services.page_status import find_translated_file
    path = find_translated_file(out_dir, "page")
    assert path.name == "page_slices.json"
```

**Step 2: Run test to verify it fails**
Run: `pytest -q tests/test_page_status.py::test_find_translated_file_prefers_slices`
Expected: FAIL

**Step 3: Implement**
- `find_translated_file`: check `<stem>_slices.json` first.
- Ensure `translate.py` uses returned path for broadcasting.
- Ensure `manga.py` resolves URL appropriately (json path).

**Step 4: Run test to verify it passes**
Run: `pytest -q tests/test_page_status.py::test_find_translated_file_prefers_slices`
Expected: PASS

**Step 5: Commit**
```bash
git add app/services/page_status.py app/routes/manga.py app/routes/translate.py tests/test_page_status.py
git commit -m "feat: support sliced webp outputs"
```

---

### Task 5: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Step 1: Update docs**
Add section describing sliced WebP behavior and index JSON location.

**Step 2: Commit**
```bash
git add README.md .env.example
git commit -m "docs: describe sliced webp output"
```

---

### Task 6: Full test run

Run:
```
pytest -q tests/test_image_io.py tests/test_image_slices.py tests/test_page_status.py
```
Expected: PASS

---

## Execution Handoff
Plan complete and saved to `docs/plans/2026-02-04-sliced-webp-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
