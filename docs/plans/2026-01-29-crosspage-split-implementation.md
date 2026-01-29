# Cross-Page Bubble Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split cross-page bubble translations into top/bottom halves with punctuation-first logic and render both pages centered.

**Architecture:** Add a cross-page splitter + pairing helper, then run a sequential batch mode that pairs edge bubbles across adjacent pages, translates once, splits by punctuation, and writes target_text back before rendering.

**Tech Stack:** Python 3, pydantic models, pytest.

### Task 1: Add punctuation-first split utility

**Files:**
- Create: `core/crosspage_splitter.py`
- Test: `tests/test_crosspage_splitter.py`

**Step 1: Write the failing test**

```python
from core.crosspage_splitter import split_by_punctuation


def test_split_by_punctuation_prefers_midpoint():
    text = "这段时间，单方面地让我很难受。"
    top, bottom = split_by_punctuation(text)
    assert top.endswith("，")
    assert bottom.startswith("单方面")


def test_split_by_punctuation_fallback_ratio():
    text = "没有标点的长句测试"
    top, bottom = split_by_punctuation(text)
    assert top
    assert bottom
    assert abs(len(top) - len(bottom)) <= 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_splitter.py -v`
Expected: FAIL with `ModuleNotFoundError` for `core.crosspage_splitter`.

**Step 3: Write minimal implementation**

```python
# core/crosspage_splitter.py
from __future__ import annotations

PUNCTUATION = ["。", "！", "？", "…", "；", "，"]


def split_by_punctuation(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    if not text:
        return "", ""
    if len(text) <= 4:
        mid = len(text) // 2
        return text[:mid], text[mid:]

    mid = len(text) // 2
    candidates = [i for i, ch in enumerate(text) if ch in PUNCTUATION]
    if candidates:
        best = min(candidates, key=lambda i: abs(i - mid))
        # keep punctuation in top
        top = text[: best + 1]
        bottom = text[best + 1 :]
        if len(top.strip()) >= 2 and len(bottom.strip()) >= 2:
            return top.strip(), bottom.strip()

    # fallback ratio split
    split = int(len(text) * 0.5)
    top = text[:split]
    bottom = text[split:]
    return top.strip(), bottom.strip()
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_splitter.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/crosspage_splitter.py tests/test_crosspage_splitter.py
git commit -m "feat: add punctuation-first crosspage splitter"
```

### Task 2: Add edge pairing helper

**Files:**
- Create: `core/crosspage_pairing.py`
- Test: `tests/test_crosspage_pairing.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData, TaskContext
from core.crosspage_pairing import find_edge_groups, match_crosspage_pairs


def _region(x1, y1, x2, y2, text):
    return RegionData(box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2), source_text=text)


def test_match_crosspage_pairs_by_x_overlap():
    ctx_top = TaskContext(image_path="/tmp/top.png")
    ctx_top.image_height = 1000
    ctx_top.image_width = 800
    ctx_top.regions = [
        _region(100, 900, 300, 980, "bottom text"),
    ]

    ctx_bottom = TaskContext(image_path="/tmp/bottom.png")
    ctx_bottom.image_height = 1000
    ctx_bottom.image_width = 800
    ctx_bottom.regions = [
        _region(110, 10, 310, 90, "top text"),
    ]

    top_groups = find_edge_groups(ctx_top, edge="bottom")
    bottom_groups = find_edge_groups(ctx_bottom, edge="top")
    pairs = match_crosspage_pairs(top_groups, bottom_groups)
    assert len(pairs) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_pairing.py -v`
Expected: FAIL with `ModuleNotFoundError`.

**Step 3: Write minimal implementation**

```python
# core/crosspage_pairing.py
from __future__ import annotations
from typing import List, Tuple
from .translator import group_adjacent_regions
from .models import Box2D, RegionData, TaskContext


def _group_box(group: List[RegionData]) -> Box2D:
    xs = [r.box_2d.x1 for r in group if r.box_2d]
    ys = [r.box_2d.y1 for r in group if r.box_2d]
    xe = [r.box_2d.x2 for r in group if r.box_2d]
    ye = [r.box_2d.y2 for r in group if r.box_2d]
    return Box2D(x1=min(xs), y1=min(ys), x2=max(xe), y2=max(ye))


def find_edge_groups(context: TaskContext, edge: str, ratio: float = 0.1):
    groups = group_adjacent_regions(context.regions)
    edge_groups = []
    for group in groups:
        if not any(r.box_2d for r in group):
            continue
        box = _group_box(group)
        if edge == "top" and box.y1 <= context.image_height * ratio:
            edge_groups.append((group, box))
        if edge == "bottom" and box.y2 >= context.image_height * (1 - ratio):
            edge_groups.append((group, box))
    return edge_groups


def match_crosspage_pairs(bottom_groups, top_groups, min_overlap: float = 0.2):
    pairs = []
    used = set()
    for bottom_group, bottom_box in bottom_groups:
        best = None
        best_score = 0
        for idx, (top_group, top_box) in enumerate(top_groups):
            if idx in used:
                continue
            overlap = max(0, min(bottom_box.x2, top_box.x2) - max(bottom_box.x1, top_box.x1))
            min_width = min(bottom_box.width, top_box.width)
            score = overlap / min_width if min_width > 0 else 0
            if score > best_score:
                best_score = score
                best = idx
        if best is not None and best_score >= min_overlap:
            used.add(best)
            pairs.append((bottom_group, top_groups[best][0]))
    return pairs
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_pairing.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/crosspage_pairing.py tests/test_crosspage_pairing.py
git commit -m "feat: add edge pairing for crosspage bubbles"
```

### Task 3: Add image size to TaskContext and set in OCR

**Files:**
- Modify: `core/models.py`
- Modify: `core/modules/ocr.py`
- Test: `tests/test_taskcontext_image_size.py`

**Step 1: Write the failing test**

```python
import asyncio
from PIL import Image

from core.models import TaskContext
from core.modules.ocr import OCRModule


def test_ocr_sets_image_size(tmp_path):
    img = tmp_path / "img.png"
    Image.new("RGB", (123, 456)).save(img)
    ctx = TaskContext(image_path=str(img))
    module = OCRModule(use_mock=True)

    asyncio.run(module.process(ctx))

    assert ctx.image_width == 123
    assert ctx.image_height == 456
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_taskcontext_image_size.py -v`
Expected: FAIL (missing attributes)

**Step 3: Implement minimal model + OCR update**

```python
# core/models.py
class TaskContext(BaseModel):
    ...
    image_width: int | None = Field(default=None)
    image_height: int | None = Field(default=None)
```

```python
# core/modules/ocr.py
with Image.open(context.image_path) as img:
    context.image_height = img.height
    context.image_width = img.width
    image_shape = (img.height, img.width)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_taskcontext_image_size.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/models.py core/modules/ocr.py tests/test_taskcontext_image_size.py
git commit -m "feat: store image size on TaskContext"
```

### Task 4: Skip translation when target_text already set

**Files:**
- Modify: `core/modules/translator.py`
- Test: `tests/test_translator_prefilled_target.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_skips_prefilled_target():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hello",
        target_text="预先填充",
    )
    ctx = TaskContext(image_path="/tmp/x.png", regions=[region])
    module = TranslatorModule(use_mock=True)

    asyncio.run(module.process(ctx))

    assert ctx.regions[0].target_text == "预先填充"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_translator_prefilled_target.py -v`
Expected: FAIL (target_text overwritten)

**Step 3: Implement minimal skip logic**

```python
# core/modules/translator.py
for group in groups:
    group = [r for r in group if not (r.target_text and r.target_text.strip())]
    if not group:
        continue
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_translator_prefilled_target.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py tests/test_translator_prefilled_target.py
git commit -m "feat: skip translation for prefilled targets"
```

### Task 5: Crosspage batch processing

**Files:**
- Modify: `core/pipeline.py`
- Create: `core/crosspage_processor.py`
- Test: `tests/test_crosspage_end_to_end.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.pipeline import Pipeline

class _MockOCR:
    async def process(self, ctx):
        return ctx

class _MockTranslator:
    async def process(self, ctx):
        return ctx
    async def translate_texts(self, texts):
        return ["你好世界"]

class _MockInpainter:
    async def process(self, ctx):
        return ctx

class _MockRenderer:
    async def process(self, ctx):
        return ctx


def test_crosspage_split_end_to_end():
    top = TaskContext(image_path="/tmp/top.png")
    top.image_height = 1000
    top.image_width = 800
    top.regions = [RegionData(box_2d=Box2D(x1=100,y1=900,x2=300,y2=980), source_text="He")]

    bottom = TaskContext(image_path="/tmp/bottom.png")
    bottom.image_height = 1000
    bottom.image_width = 800
    bottom.regions = [RegionData(box_2d=Box2D(x1=110,y1=10,x2=310,y2=90), source_text="llo")]

    pipeline = Pipeline(
        ocr=_MockOCR(),
        translator=_MockTranslator(),
        inpainter=_MockInpainter(),
        renderer=_MockRenderer(),
    )

    results = asyncio.run(pipeline.process_batch_crosspage([top, bottom]))
    assert results[0].task.regions[0].target_text
    assert results[1].task.regions[0].target_text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_end_to_end.py -v`
Expected: FAIL (method not found)

**Step 3: Implement minimal crosspage processor**

```python
# core/crosspage_processor.py
from .crosspage_pairing import find_edge_groups, match_crosspage_pairs
from .crosspage_splitter import split_by_punctuation

async def apply_crosspage_split(translator, ctx_a, ctx_b):
    bottom_groups = find_edge_groups(ctx_a, edge="bottom")
    top_groups = find_edge_groups(ctx_b, edge="top")
    pairs = match_crosspage_pairs(bottom_groups, top_groups)
    if not pairs:
        return
    for bottom_group, top_group in pairs:
        combined = " ".join([r.source_text for r in bottom_group + top_group if r.source_text])
        translation = (await translator.translate_texts([combined]))[0]
        top_text, bottom_text = split_by_punctuation(translation)
        # assign to largest region in each group
        def assign(group, text):
            largest = max(group, key=lambda r: r.box_2d.width * r.box_2d.height)
            largest.target_text = text
            for r in group:
                if r is not largest:
                    r.target_text = "[INPAINT_ONLY]"
        assign(bottom_group, top_text)
        assign(top_group, bottom_text)
```

```python
# core/pipeline.py
    async def process_batch_crosspage(self, contexts):
        # OCR first
        for ctx in contexts:
            ctx = await self.ocr.process(ctx)
        # crosspage split across pairs
        for i in range(len(contexts) - 1):
            await apply_crosspage_split(self.translator, contexts[i], contexts[i + 1])
        # translator for remaining
        for ctx in contexts:
            ctx = await self.translator.process(ctx)
        # inpaint + render
        results = []
        for ctx in contexts:
            ctx = await self.inpainter.process(ctx)
            ctx = await self.renderer.process(ctx)
            results.append(ctx)
        return results
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_end_to_end.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/pipeline.py core/crosspage_processor.py tests/test_crosspage_end_to_end.py
git commit -m "feat: crosspage batch split pipeline"
```

### Task 6: Full test run

**Step 1: Run tests**

Run: `pytest -q`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```

---

Plan complete and saved to `docs/plans/2026-01-29-crosspage-split-implementation.md`.

Two execution options:

1. Subagent-Driven (this session)
2. Parallel Session (separate)

Which approach?
