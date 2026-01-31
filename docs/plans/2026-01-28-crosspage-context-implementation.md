# Cross-Page Context Implementation Plan (Edge Bands)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在长图切页场景中使用“上下边界带 OCR”连接跨页气泡文本，减少语义断裂与重复翻译。

**Architecture:** 对当前页 OCR 结果标注“边界带坐标”，同时对相邻页的顶/底边界带做轻量 OCR。用边界带坐标匹配跨页文本，将相邻页文本作为 context 附加到当前页翻译，并在下一页顶部区域标记 `skip_translation` 防止重复渲染。

**Tech Stack:** Python 3, pydantic models, pytest.

---

### Task 1: RegionData 增加跨页辅助字段

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
from core.models import RegionData, Box2D

def test_regiondata_accepts_crosspage_fields():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hi",
        edge_role="current_bottom",
        edge_box_2d=Box2D(x1=0, y1=-10, x2=10, y2=0),
        skip_translation=True,
        crosspage_texts=["next part"],
    )
    assert region.edge_role == "current_bottom"
    assert region.edge_box_2d.y1 == -10
    assert region.skip_translation is True
    assert region.crosspage_texts == ["next part"]
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_regiondata_accepts_crosspage_fields -v`
Expected: FAIL (unexpected field or missing attribute).

**Step 3: Write minimal implementation**

Add optional fields to `RegionData`:
- `edge_role: Optional[str] = None`
- `edge_box_2d: Optional[Box2D] = None`
- `skip_translation: bool = False`
- `crosspage_texts: Optional[list[str]] = None`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_regiondata_accepts_crosspage_fields -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/models.py tests/test_crosspage_context.py
git commit -m "feat: add crosspage region fields"
```

---

### Task 2: 边界带坐标与跨页匹配工具

**Files:**
- Modify: `core/vision/ocr/postprocessing.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
from core.models import RegionData, Box2D
from core.vision.ocr.postprocessing import build_edge_box, match_crosspage_regions


def test_build_edge_box_bottom_band():
    region = RegionData(box_2d=Box2D(x1=0, y1=90, x2=10, y2=100))
    edge = build_edge_box(region, band_height=20, image_height=100, edge="bottom")
    assert edge.y1 == -10 and edge.y2 == 0


def test_match_crosspage_regions_by_edge_box():
    bottom = RegionData(edge_box_2d=Box2D(x1=0, y1=-8, x2=10, y2=-2))
    top = RegionData(edge_box_2d=Box2D(x1=1, y1=1, x2=9, y2=7))
    assert match_crosspage_regions(bottom, top, x_overlap=0.5, y_gap=5) is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_build_edge_box_bottom_band -v`
Expected: FAIL (function missing).

**Step 3: Write minimal implementation**

Add helpers in `core/vision/ocr/postprocessing.py`:
- `build_edge_box(region, band_height, image_height, edge)`
- `match_crosspage_regions(a, b, x_overlap, y_gap)`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_build_edge_box_bottom_band -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/vision/ocr/postprocessing.py tests/test_crosspage_context.py
git commit -m "feat: add edge-box helpers for crosspage matching"
```

---

### Task 3: OCR 边界带识别（相邻页）

**Files:**
- Modify: `core/vision/ocr/paddle_engine.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
from core.vision.ocr.paddle_engine import PaddleOCREngine


def test_detect_and_recognize_band_accepts_edge(tmp_path, monkeypatch):
    engine = PaddleOCREngine(lang="en")
    # just assert method exists and returns list
    assert hasattr(engine, "detect_and_recognize_band")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_detect_and_recognize_band_accepts_edge -v`
Expected: FAIL (method missing).

**Step 3: Write minimal implementation**

Add `detect_and_recognize_band(image_path, edge, band_height)` using cv2 crop + `_process_chunk`.
Return list of RegionData with `box_2d` in band coordinates.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_detect_and_recognize_band_accepts_edge -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/vision/ocr/paddle_engine.py tests/test_crosspage_context.py
git commit -m "feat: add edge-band OCR helper"
```

---

### Task 4: OCRModule 注入跨页上下文

**Files:**
- Modify: `core/modules/ocr.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import TaskContext, RegionData, Box2D
from core.modules.ocr import OCRModule


def test_ocr_module_marks_skip_translation_on_top_band(monkeypatch):
    module = OCRModule(use_mock=True)
    # mock engine to return a top-band-like region
    async def fake_detect(path):
        return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="X")]
    module.engine.detect_and_recognize = fake_detect

    ctx = TaskContext(image_path="/tmp/2.jpg", source_language="en")
    result = asyncio.run(module.process(ctx))
    # crosspage hook should set flags if matched; at least ensure field exists
    assert all(hasattr(r, "skip_translation") for r in result.regions)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_ocr_module_marks_skip_translation_on_top_band -v`
Expected: FAIL (field missing or hook missing).

**Step 3: Write minimal implementation**

In `OCRModule.process()`:
- 找到同目录相邻页（文件名数字排序）
- OCR 当前页后，OCR 前一页底带、后一页顶带（若存在）
- 为当前页顶部区域匹配上一页底带，命中则 `skip_translation=True`
- 为当前页底部区域匹配下一页顶带，命中则 `crosspage_texts.append(next_text)`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_ocr_module_marks_skip_translation_on_top_band -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/ocr.py tests/test_crosspage_context.py
git commit -m "feat: inject crosspage OCR context"
```

---

### Task 5: 翻译阶段利用跨页上下文 + 跳过标记

**Files:**
- Modify: `core/modules/translator.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import TaskContext, RegionData, Box2D
from core.modules.translator import TranslatorModule


def test_translator_appends_crosspage_texts_and_skips():
    a = RegionData(box_2d=Box2D(x1=0,y1=0,x2=10,y2=10), source_text="A", crosspage_texts=["B"])
    b = RegionData(box_2d=Box2D(x1=0,y1=0,x2=10,y2=10), source_text="C", skip_translation=True)
    ctx = TaskContext(image_path="/tmp/x.png", regions=[a, b])
    module = TranslatorModule(use_mock=True)
    result = asyncio.run(module.process(ctx))
    assert "B" in result.regions[0].target_text
    assert result.regions[1].target_text == ""
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_translator_appends_crosspage_texts_and_skips -v`
Expected: FAIL

**Step 3: Write minimal implementation**

In `TranslatorModule.process()`:
- 若 `region.skip_translation` → `target_text = ""`
- 合并文本时，附加 `crosspage_texts`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_translator_appends_crosspage_texts_and_skips -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py tests/test_crosspage_context.py
git commit -m "feat: use crosspage context in translator"
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
