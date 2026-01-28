# Inpaint Mode "Erase" Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure regions with `inpaint_mode="erase"` are always inpainted even when `target_text` is empty, while SFX regions are never inpainted.

**Architecture:** Update `core/modules/inpainter.py` to select regions based on `inpaint_mode`, `target_text`, and `is_sfx`. Add a unit test with a dummy inpainter to verify selection logic without real image IO.

**Tech Stack:** Python 3, pytest, pydantic models.

### Task 1: Add failing test for inpainting selection rules

**Files:**
- Create: `tests/test_inpainter_module.py`

**Step 1: Write the failing test**

```python
import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.inpainter import InpainterModule


class _DummyInpainter:
    def __init__(self):
        self.regions = None

    async def inpaint_regions(self, image_path, regions, output_path, temp_dir, dilation):
        self.regions = regions
        return output_path


def test_inpainter_selects_regions_for_erase_and_replace(tmp_path):
    dummy = _DummyInpainter()
    module = InpainterModule(inpainter=dummy, output_dir=str(tmp_path), use_time_subdir=False)

    r_erase = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="wm",
        target_text="",
        inpaint_mode="erase",
    )
    r_replace = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=20, y2=20),
        source_text="hi",
        target_text="你好",
        is_sfx=False,
    )
    r_sfx = RegionData(
        box_2d=Box2D(x1=20, y1=20, x2=30, y2=30),
        source_text="BANG",
        target_text="[SFX: BANG]",
        is_sfx=True,
    )
    r_empty = RegionData(
        box_2d=Box2D(x1=30, y1=30, x2=40, y2=40),
        source_text="empty",
        target_text="",
        inpaint_mode="replace",
    )

    ctx = TaskContext(image_path="/tmp/input.png", regions=[r_erase, r_replace, r_sfx, r_empty])
    asyncio.run(module.process(ctx))

    selected = {r.region_id for r in (dummy.regions or [])}
    assert selected == {r_erase.region_id, r_replace.region_id}
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_inpainter_module.py::test_inpainter_selects_regions_for_erase_and_replace -v`
Expected: FAIL (erase region not selected, SFX selected)

**Step 3: Commit**

```bash
git add tests/test_inpainter_module.py
git commit -m "test: cover inpaint selection rules"
```

### Task 2: Implement inpaint selection logic in InpainterModule

**Files:**
- Modify: `core/modules/inpainter.py`

**Step 1: Implement minimal selection logic**

Replace current `regions_to_inpaint` computation with:

```python
        def _should_inpaint(region) -> bool:
            if getattr(region, "is_sfx", False):
                return False
            if getattr(region, "inpaint_mode", "replace") == "erase":
                return True
            return bool(region.target_text)

        regions_to_inpaint = [r for r in context.regions if _should_inpaint(r)]
```

(Optional) Update the log message to avoid mentioning only SFX.

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_inpainter_module.py::test_inpainter_selects_regions_for_erase_and_replace -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/modules/inpainter.py
git commit -m "feat: honor inpaint_mode erase in inpainter"
```

### Task 3: Full test run

**Step 1: Run tests**

Run: `pytest -v tests`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
