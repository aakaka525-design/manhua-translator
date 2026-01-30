# Debug Artifacts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在开发模式输出多阶段调试图（含 OCR 文本标签与翻译阶段），帮助快速定位流程问题。  
**Architecture:** 新增 `core/debug_artifacts.py` 统一写图与 `manifest.json`，各模块在阶段结束后调用。通过 `DEBUG_ARTIFACTS=1` 开关控制。  
**Tech Stack:** Python 3, PIL, pytest

### Task 1: 新增 DebugArtifactWriter + OCR 标注图

**Files:**
- Create: `core/debug_artifacts.py`
- Create: `tests/test_debug_artifacts.py`

**Step 1: 写失败测试（OCR 标签输出）**

```python
from pathlib import Path
from PIL import Image

from core.models import Box2D, RegionData, TaskContext


def test_debug_writer_outputs_ocr_boxes(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=10, y1=10, x2=80, y2=40),
            source_text="HELLO",
            normalized_text="Hello",
            confidence=0.9,
        )
    ]

    from core.debug_artifacts import DebugArtifactWriter
    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    output = writer.write_ocr(ctx, image_path=str(img_path))

    assert output.exists()
```

**Step 2: 运行测试，确认失败**

Run: `pytest tests/test_debug_artifacts.py::test_debug_writer_outputs_ocr_boxes -v`  
Expected: FAIL (模块不存在或方法缺失)

**Step 3: 最小实现**

```python
# core/debug_artifacts.py
import os
import json
from pathlib import Path
from typing import Optional
from PIL import Image, ImageDraw, ImageFont


class DebugArtifactWriter:
    def __init__(self, output_dir: str = "output/debug", enabled: Optional[bool] = None):
        self.enabled = enabled if enabled is not None else os.getenv("DEBUG_ARTIFACTS") == "1"
        self.output_dir = Path(output_dir)

    def _task_dir(self, task_id: str) -> Path:
        return self.output_dir / str(task_id)

    def _ensure_dir(self, task_id: str) -> Path:
        task_dir = self._task_dir(task_id)
        task_dir.mkdir(parents=True, exist_ok=True)
        return task_dir

    def _font(self) -> ImageFont.ImageFont:
        try:
            return ImageFont.load_default()
        except Exception:
            return ImageFont.load_default()

    def _truncate(self, text: str, max_len: int = 24) -> str:
        if not text:
            return ""
        text = text.replace("\n", " ").strip()
        return text if len(text) <= max_len else text[: max_len - 1] + "…"

    def _draw_regions(self, image_path: str, regions, label_getter, color: str, out_path: Path):
        img = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(img)
        font = self._font()
        for r in regions:
            if not r.box_2d:
                continue
            box = r.box_2d
            draw.rectangle([box.x1, box.y1, box.x2, box.y2], outline=color, width=2)
            label = self._truncate(label_getter(r) or "")
            if label:
                text_w, text_h = draw.textbbox((0, 0), label, font=font)[2:]
                x = box.x1
                y = max(0, box.y1 - text_h - 4)
                draw.rectangle([x, y, x + text_w + 6, y + text_h + 4], fill="white")
                draw.text((x + 3, y + 2), label, font=font, fill="black")
        img.save(out_path)

    def write_ocr(self, context, image_path: str):
        if not self.enabled:
            return None
        task_dir = self._ensure_dir(context.task_id)
        out_path = task_dir / "01_ocr_boxes.png"
        def label(r):
            return r.normalized_text or r.source_text or ""
        self._draw_regions(image_path, context.regions, label, "#00A0FF", out_path)
        return out_path
```

**Step 4: 运行测试，确认通过**

Run: `pytest tests/test_debug_artifacts.py::test_debug_writer_outputs_ocr_boxes -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/debug_artifacts.py tests/test_debug_artifacts.py
git commit -m "feat: add debug artifact writer for OCR stage"
```

---

### Task 2: 增加翻译阶段图（target_text 标签）

**Files:**
- Modify: `core/debug_artifacts.py`
- Modify: `tests/test_debug_artifacts.py`

**Step 1: 写失败测试**

```python
def test_debug_writer_outputs_translation_boxes(tmp_path: Path):
    img_path = tmp_path / "blank.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    ctx = TaskContext(image_path=str(img_path))
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=10, y1=10, x2=80, y2=40),
            target_text="你好",
        )
    ]

    from core.debug_artifacts import DebugArtifactWriter
    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=True)
    out_path = writer.write_translation(ctx, image_path=str(img_path))

    assert out_path.exists()
```

**Step 2: Run test to verify it fails**  
Run: `pytest tests/test_debug_artifacts.py::test_debug_writer_outputs_translation_boxes -v`  
Expected: FAIL (method not found)

**Step 3: Minimal implementation**

```python
def write_translation(self, context, image_path: str):
    if not self.enabled:
        return None
    task_dir = self._ensure_dir(context.task_id)
    out_path = task_dir / "04_translate.png"
    def label(r):
        return r.target_text or ""
    self._draw_regions(image_path, context.regions, label, "#FF8C00", out_path)
    return out_path
```

**Step 4: Run test to verify it passes**  
Run: `pytest tests/test_debug_artifacts.py::test_debug_writer_outputs_translation_boxes -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/debug_artifacts.py tests/test_debug_artifacts.py
git commit -m "feat: add translation debug artifact"
```

---

### Task 3: Inpaint mask 输出支持

**Files:**
- Modify: `core/vision/inpainter.py`
- Modify: `core/modules/inpainter.py`
- Modify: `core/models.py`
- Modify: `tests/test_inpainter_mask_path.py` (new)

**Step 1: 写失败测试**

```python
from core.models import Box2D, RegionData
from core.vision.inpainter import OpenCVInpainter


def test_inpaint_regions_returns_mask_path(tmp_path):
    # 使用 10x10 空白图
    from PIL import Image
    img_path = tmp_path / "img.png"
    Image.new("RGB", (20, 20), "white").save(img_path)

    regions = [RegionData(box_2d=Box2D(x1=2, y1=2, x2=6, y2=6))]
    inp = OpenCVInpainter()
    out_path = tmp_path / "out.png"

    result_path, mask_path = asyncio.run(
        inp.inpaint_regions(str(img_path), regions, str(out_path), str(tmp_path))
    )

    assert Path(mask_path).exists()
```

**Step 2: Run test to verify it fails**  
Run: `pytest tests/test_inpainter_mask_path.py::test_inpaint_regions_returns_mask_path -v`  
Expected: FAIL (return signature mismatch)

**Step 3: Minimal implementation**

- 修改 `inpaint_regions()` 返回 `(output_path, mask_path)`  
- `TaskContext` 新增 `mask_path: Optional[str]`  
- `InpainterModule.process()` 接收 mask_path 并保存到 `context.mask_path`

**Step 4: Run test to verify it passes**  
Run: `pytest tests/test_inpainter_mask_path.py::test_inpaint_regions_returns_mask_path -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/vision/inpainter.py core/modules/inpainter.py core/models.py tests/test_inpainter_mask_path.py
git commit -m "feat: expose combined inpaint mask path"
```

---

### Task 4: 集成阶段输出（OCR/分组/翻译/Inpaint/渲染）

**Files:**
- Modify: `core/modules/ocr.py`
- Modify: `core/modules/translator.py`
- Modify: `core/modules/inpainter.py`
- Modify: `core/modules/renderer.py`
- Modify: `core/debug_artifacts.py`

**Step 1: 写失败测试（DEBUG_ARTIFACTS 关闭时不写文件）**

```python
def test_debug_writer_disabled_no_output(tmp_path: Path):
    from core.debug_artifacts import DebugArtifactWriter
    writer = DebugArtifactWriter(output_dir=tmp_path, enabled=False)
    assert writer.write_ocr(TaskContext(image_path="x"), "x") is None
```

**Step 2: Run test to verify it fails**  
Run: `pytest tests/test_debug_artifacts.py::test_debug_writer_disabled_no_output -v`  
Expected: FAIL (method not handling disabled)

**Step 3: Minimal integration**

- OCR 结束后调用 `write_ocr`  
- Translator 翻译完成后调用 `write_translation`  
- Inpaint 完成后调用 `write_mask` 与 `write_inpainted`  
- Renderer 完成后调用 `write_layout` 与 `write_final`  
（`write_grouping` 可用 render_box_2d 标注）

**Step 4: Run tests**  
Run: `pytest tests/test_debug_artifacts.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/ocr.py core/modules/translator.py core/modules/inpainter.py core/modules/renderer.py core/debug_artifacts.py tests/test_debug_artifacts.py
git commit -m "feat: integrate debug artifacts across pipeline"
```

---

### Task 5: 文档更新

**Files:**
- Modify: `README.md`

**Step 1: 更新 README**
- 增加 `DEBUG_ARTIFACTS=1` 的说明  
- 说明 `output/debug/<task_id>/` 产物与 `manifest.json`

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: describe debug artifacts output"
```

---

### Task 6: 全量测试

**Step 1: Run tests**  
Run: `pytest -q`  
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```

---

Plan complete and saved to `docs/plans/2026-01-30-debug-artifacts-implementation.md`.

Two execution options:
1) Subagent-Driven (this session)  
2) Parallel Session (separate)  

Which approach?
