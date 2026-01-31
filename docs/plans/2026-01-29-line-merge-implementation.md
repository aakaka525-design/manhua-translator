# Line Merge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在翻译前合并同字幕框内的 OCR 碎片（不保留换行），让擦除与渲染以合并后的区域为准。

**Architecture:** 使用 `group_adjacent_regions()` 先做气泡分组，再在每个分组内做“行内聚类 + 合并”，输出新的 Region 列表并替换 `context.regions`。翻译阶段继续使用分组逻辑，但基于合并后的 regions。

**Tech Stack:** Python 3, Pydantic models, pytest.

---

### Task 1: 添加 LineMerger 单元测试（失败测试）

**Files:**
- Create: `tests/test_line_merger.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData
from core.text_merge.line_merger import merge_line_regions


def test_line_merger_merges_same_row_fragments():
    r1 = RegionData(box_2d=Box2D(x1=10, y1=100, x2=60, y2=130), source_text="너무", confidence=0.9)
    r2 = RegionData(box_2d=Box2D(x1=70, y1=102, x2=120, y2=132), source_text="좋아", confidence=0.9)
    merged = merge_line_regions([[r1, r2]])

    assert len(merged) == 1
    assert merged[0].source_text == "너무좋아"
    assert merged[0].box_2d.x1 == 10
    assert merged[0].box_2d.x2 == 120
    assert merged[0].box_2d.y1 == 100
    assert merged[0].box_2d.y2 == 132
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_line_merger.py::test_line_merger_merges_same_row_fragments -v`

Expected: FAIL with `ModuleNotFoundError` or missing function.

---

### Task 2: 添加负样例与水印排除测试（失败测试）

**Files:**
- Modify: `tests/test_line_merger.py`

**Step 1: Write the failing tests**

```python
from core.models import Box2D, RegionData
from core.text_merge.line_merger import merge_line_regions


def test_line_merger_skips_watermark_regions():
    r1 = RegionData(box_2d=Box2D(x1=10, y1=100, x2=60, y2=130), source_text="너무", confidence=0.9)
    wm = RegionData(box_2d=Box2D(x1=500, y1=20, x2=680, y2=50), source_text="NEWTOKI", confidence=0.9, is_watermark=True)
    merged = merge_line_regions([[r1, wm]])

    # watermark 不参与合并，结果应保留两条
    assert len(merged) == 2
    assert any(r.source_text == "NEWTOKI" for r in merged)


def test_line_merger_does_not_merge_when_height_diff_large():
    r1 = RegionData(box_2d=Box2D(x1=10, y1=100, x2=60, y2=130), source_text="너무", confidence=0.9)
    r2 = RegionData(box_2d=Box2D(x1=70, y1=100, x2=180, y2=200), source_text="좋아", confidence=0.9)
    merged = merge_line_regions([[r1, r2]])

    # 高度差过大时不合并
    assert len(merged) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_line_merger.py::test_line_merger_skips_watermark_regions -v`

Expected: FAIL.

---

### Task 3: 实现 LineMerger（最小可用）

**Files:**
- Create: `core/text_merge/__init__.py`
- Create: `core/text_merge/line_merger.py`

**Step 1: Write minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List
from uuid import uuid4

from ..models import Box2D, RegionData


ROW_GAP_RATIO = 0.6
X_GAP_RATIO = 0.8
HEIGHT_RATIO = 0.5
MAX_HEIGHT_RATIO = 2.0
MIN_CONFIDENCE = 0.4


@dataclass
class _Row:
    regions: list[RegionData]
    center_y: float


def _median(values: list[int]) -> float:
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return float(values[mid])
    return (values[mid - 1] + values[mid]) / 2.0


def _union_box(regions: Iterable[RegionData]) -> Box2D:
    xs = [r.box_2d.x1 for r in regions if r.box_2d]
    ys = [r.box_2d.y1 for r in regions if r.box_2d]
    xe = [r.box_2d.x2 for r in regions if r.box_2d]
    ye = [r.box_2d.y2 for r in regions if r.box_2d]
    return Box2D(x1=min(xs), y1=min(ys), x2=max(xe), y2=max(ye))


def _join_texts(texts: list[str]) -> str:
    # CJK 不插空格，英数字之间插入单空格
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        if out[-1].isascii() and t[0].isascii():
            out += " " + t
        else:
            out += t
    return out


def merge_line_regions(groups: list[list[RegionData]]) -> list[RegionData]:
    merged_regions: list[RegionData] = []

    for group in groups:
        candidates = [
            r for r in group
            if r.box_2d and r.source_text and not r.is_watermark and not r.is_sfx and r.confidence >= MIN_CONFIDENCE
        ]
        excluded = [r for r in group if r not in candidates]

        if len(candidates) <= 1:
            merged_regions.extend(group)
            continue

        heights = [r.box_2d.height for r in candidates if r.box_2d]
        if not heights:
            merged_regions.extend(group)
            continue

        median_h = _median(heights)
        if median_h <= 0:
            merged_regions.extend(group)
            continue
        if max(heights) / max(1, min(heights)) > MAX_HEIGHT_RATIO:
            merged_regions.extend(group)
            continue

        # row clustering by y center
        rows: list[_Row] = []
        for r in sorted(candidates, key=lambda x: (x.box_2d.y1, x.box_2d.x1)):
            center_y = (r.box_2d.y1 + r.box_2d.y2) / 2
            placed = False
            for row in rows:
                if abs(center_y - row.center_y) <= ROW_GAP_RATIO * median_h:
                    row.regions.append(r)
                    row.center_y = sum(
                        (reg.box_2d.y1 + reg.box_2d.y2) / 2 for reg in row.regions
                    ) / len(row.regions)
                    placed = True
                    break
            if not placed:
                rows.append(_Row([r], center_y))

        # flatten rows into ordered list
        rows.sort(key=lambda r: r.center_y)
        ordered = []
        for row in rows:
            row.regions.sort(key=lambda r: r.box_2d.x1)
            ordered.extend(row.regions)

        # ensure gaps are reasonable; if not, skip merge
        for left, right in zip(ordered, ordered[1:]):
            x_gap = right.box_2d.x1 - left.box_2d.x2
            if x_gap > X_GAP_RATIO * median_h:
                merged_regions.extend(group)
                break
        else:
            merged_text = _join_texts([r.source_text for r in ordered])
            base = max(ordered, key=lambda r: r.box_2d.width * r.box_2d.height)
            merged = base.model_copy(deep=True)
            merged.region_id = uuid4()
            merged.source_text = merged_text
            merged.normalized_text = merged_text
            merged.box_2d = _union_box(ordered)
            merged.render_box_2d = None
            merged.confidence = sum(r.confidence for r in ordered) / len(ordered)
            merged_regions.append(merged)
            merged_regions.extend(excluded)

    return merged_regions
```

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_line_merger.py -v`

Expected: PASS.

**Step 3: Commit**

```bash
git add core/text_merge/line_merger.py core/text_merge/__init__.py tests/test_line_merger.py
git commit -m "feat: add line-level OCR merge"
```

---

### Task 4: 集成到 Translator（失败测试）

**Files:**
- Modify: `core/modules/translator.py`
- Modify: `tests/test_translator_line_merge.py` (new)

**Step 1: Write the failing test**

```python
import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_translator_merges_line_fragments_before_translate():
    ctx = TaskContext(image_path="/tmp/input.png")
    ctx.regions = [
        RegionData(box_2d=Box2D(x1=10, y1=100, x2=60, y2=130), source_text="너무", confidence=0.9),
        RegionData(box_2d=Box2D(x1=70, y1=102, x2=120, y2=132), source_text="좋아", confidence=0.9),
    ]
    module = TranslatorModule(use_mock=True)
    result = asyncio.run(module.process(ctx))

    merged_texts = [r.source_text for r in result.regions]
    assert "너무좋아" in merged_texts
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_translator_line_merge.py::test_translator_merges_line_fragments_before_translate -v`

Expected: FAIL (no merge yet).

---

### Task 5: 集成 LineMerger 到 Translator

**Files:**
- Modify: `core/modules/translator.py`

**Step 1: Implement minimal integration**

```python
from ..text_merge.line_merger import merge_line_regions

# ... inside process(), after group_adjacent_regions
raw_groups = group_adjacent_regions(context.regions)
context.regions = merge_line_regions(raw_groups)
# 再次分组用于翻译
groups = group_adjacent_regions(context.regions)
```

**Step 2: Run tests**

Run: `pytest tests/test_line_merger.py tests/test_translator_line_merge.py -v`

Expected: PASS.

**Step 3: Commit**

```bash
git add core/modules/translator.py tests/test_translator_line_merge.py
git commit -m "feat: merge line fragments before translation"
```

---

### Task 6: 全量测试

**Step 1: Run tests**

Run: `pytest -q`

Expected: PASS (warnings ok).

---

Plan complete.
