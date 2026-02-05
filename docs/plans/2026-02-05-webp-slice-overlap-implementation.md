# WebP Slice Overlap Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make WebP slice overlap configurable via `WEBP_SLICE_OVERLAP` (default 10) and reflect it in `*_slices.json`.

**Architecture:** Read the overlap from environment when slicing oversized WebP outputs. Use this value for slice computation and write it into the JSON index for frontends.

**Tech Stack:** Python, Pillow, NumPy, existing image IO helpers.

---

### Task 1: Add overlap env handling + unit test

**Files:**
- Modify: `core/image_io.py`
- Modify: `tests/test_image_io.py`

**Step 1: Write the failing test**

Add to `tests/test_image_io.py`:
```python
def test_save_image_webp_oversize_respects_overlap_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    monkeypatch.setenv("WEBP_SLICE_OVERLAP", "10")
    import numpy as np
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)
    path = tmp_path / "out.png"
    saved = save_image(arr, str(path), purpose="final")
    assert saved.endswith("_slices.json")
    data = json.loads(Path(saved).read_text())
    assert data["overlap"] == 10
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_image_io.py::test_save_image_webp_oversize_respects_overlap_env`  
Expected: FAIL (overlap still 32)

**Step 3: Implement minimal code**

In `core/image_io.py`:
```python
def _webp_slice_overlap() -> int:
    return int(os.getenv("WEBP_SLICE_OVERLAP", "10"))
```

Then in `save_image` when calling `_save_webp_slices`, pass `overlap=_webp_slice_overlap()`.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_image_io.py::test_save_image_webp_oversize_respects_overlap_env`  
Expected: PASS

**Step 5: Commit**
```bash
git add core/image_io.py tests/test_image_io.py
git commit -m "feat: make webp slice overlap configurable"
```

---

### Task 2: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Step 1: Update docs**
- Add `WEBP_SLICE_OVERLAP=10` to `.env.example`.
- In `README.md` output format section, mention this variable and that `*_slices.json` uses it.

**Step 2: Commit**
```bash
git add README.md .env.example
git commit -m "docs: add webp slice overlap env"
```

---

### Task 3: Focused test run

Run:
```
pytest -q tests/test_image_io.py tests/test_image_slices.py tests/test_page_status.py
```
Expected: PASS

---

## Execution Handoff
Plan complete and saved to `docs/plans/2026-02-05-webp-slice-overlap-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration  
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
