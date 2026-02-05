# NCNN Tile Super-Resolution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Apply `UPSCALE_TILE` to NCNN backend (`-t <tile>`) so full-image super-resolution can run in tile mode and avoid seam artifacts before slicing.

**Architecture:** Reuse existing `UPSCALE_TILE` configuration. In `_run_ncnn`, include `-t` when tile > 0, log it, and store in `last_metrics`.

**Tech Stack:** Python, subprocess, existing UpscaleModule.

---

### Task 1: Add unit test for NCNN tile argument

**Files:**
- Modify: `tests/test_upscaler_module.py`
- Modify: `core/modules/upscaler.py`

**Step 1: Write the failing test**

Add to `tests/test_upscaler_module.py`:
```python
def test_upscale_ncnn_uses_tile_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_BACKEND", "ncnn")
    monkeypatch.setenv("UPSCALE_TILE", "256")
    monkeypatch.setenv("UPSCALE_MODEL", "realesr-animevideov3-x4")
    monkeypatch.setenv("UPSCALE_NCNN_MODEL_DIR", str(tmp_path))
    monkeypatch.setenv("UPSCALE_BINARY_PATH", str(tmp_path / "realesrgan-ncnn-vulkan"))

    # dummy binary + model dir
    bin_path = tmp_path / "realesrgan-ncnn-vulkan"
    bin_path.write_text("x")
    bin_path.chmod(0o755)

    # dummy model files expected by ncnn (directory must exist)
    (tmp_path / "models").mkdir(exist_ok=True)

    # fake image
    import numpy as np
    from PIL import Image
    img_path = tmp_path / "in.png"
    Image.fromarray(np.zeros((10, 10, 3), dtype=np.uint8)).save(img_path)

    # stub subprocess.run to capture args
    import core.modules.upscaler as upscaler
    captured = {}
    def _run(cmd, **kwargs):
        captured["cmd"] = cmd
        class Result: stderr = ""
        return Result()
    monkeypatch.setattr(upscaler.subprocess, "run", _run)

    from core.models import TaskContext
    ctx = TaskContext(image_path=str(img_path), output_path=str(img_path))
    up = upscaler.UpscaleModule()
    up._run_ncnn(ctx, img_path)
    assert "-t" in captured["cmd"]
    idx = captured["cmd"].index("-t")
    assert captured["cmd"][idx + 1] == "256"
```

**Step 2: Run test to verify it fails**

Run: `pytest -q tests/test_upscaler_module.py::test_upscale_ncnn_uses_tile_flag`  
Expected: FAIL (no `-t` in args)

**Step 3: Implement minimal code**

In `core/modules/upscaler.py` `_run_ncnn`:
```python
tile = int(os.getenv("UPSCALE_TILE", str(DEFAULT_TILE)))
if tile > 0:
    cmd.extend(["-t", str(tile)])
```

Also add `tile` to log line and `last_metrics`.

**Step 4: Run test to verify it passes**

Run: `pytest -q tests/test_upscaler_module.py::test_upscale_ncnn_uses_tile_flag`  
Expected: PASS

**Step 5: Commit**
```bash
git add core/modules/upscaler.py tests/test_upscaler_module.py
git commit -m "feat: support ncnn tile via UPSCALE_TILE"
```

---

### Task 2: Documentation updates

**Files:**
- Modify: `README.md`
- Modify: `.env.example`

**Step 1: Update docs**
- Note that `UPSCALE_TILE` applies to NCNN and PyTorch backends.
- No new variables required.

**Step 2: Commit**
```bash
git add README.md .env.example
git commit -m "docs: clarify UPSCALE_TILE applies to ncnn"
```

---

### Task 3: Focused test run

Run:
```
pytest -q tests/test_upscaler_module.py
```
Expected: PASS

---

## Execution Handoff
Plan complete and saved to `docs/plans/2026-02-05-ncnn-tile-superres-implementation.md`. Two execution options:

1. Subagent-Driven (this session) - I dispatch fresh subagent per task, review between tasks, fast iteration  
2. Parallel Session (separate) - Open new session with executing-plans, batch execution with checkpoints

Which approach?
