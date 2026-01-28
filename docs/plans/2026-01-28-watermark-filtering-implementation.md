# Watermark Filtering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect watermark regions, skip their translation, and erase them during inpainting.

**Architecture:** Add `core/watermark_detector.py` to apply rule-based detection (keyword/URL, position, repeat). Extend RegionData with `is_watermark` and `inpaint_mode`, integrate detector between OCR and Translation, and ensure Inpainting respects `inpaint_mode`.

**Tech Stack:** Python 3, pytest, pydantic models.

### Task 1: Add failing test for watermark keyword detection (case-insensitive)

**Files:**
- Create: `tests/test_watermark_detector.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData


def test_watermark_detector_keyword_case_insensitive():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=100, y2=50), source_text="MangaForFree.COM"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_keyword_case_insensitive -v`
Expected: FAIL (module not found or flag missing).

**Step 3: Commit**

```bash
git add tests/test_watermark_detector.py
git commit -m "test: add watermark keyword detection"
```

### Task 2: Implement minimal WatermarkDetector + RegionData fields

**Files:**
- Create: `core/watermark_detector.py`
- Modify: `core/models.py`

**Step 1: Implement minimal detector**

```python
class WatermarkDetector:
    def __init__(self, keywords=None):
        self.keywords = set([k.lower() for k in (keywords or [])])

    def detect(self, regions, image_shape):
        for r in regions:
            text = (r.source_text or "").lower()
            if any(k in text for k in self.keywords):
                r.is_watermark = True
                r.inpaint_mode = "erase"
        return regions
```

**Step 2: Extend RegionData**

Add fields:
- `is_watermark: bool = False`
- `inpaint_mode: str = "replace"`

**Step 3: Run test to verify it passes**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_keyword_case_insensitive -v`
Expected: PASS

**Step 4: Commit**

```bash
git add core/watermark_detector.py core/models.py
git commit -m "feat: add minimal watermark detector"
```

### Task 3: Add failing test for position + short text heuristic

**Files:**
- Modify: `tests/test_watermark_detector.py`

**Step 1: Write failing test**

```python
def test_watermark_detector_position_short_text():
    from core.watermark_detector import WatermarkDetector

    regions = [
        RegionData(box_2d=Box2D(x1=5, y1=950, x2=120, y2=980), source_text="toongod"),
    ]
    detector = WatermarkDetector()
    result = detector.detect(regions, image_shape=(1000, 800))

    assert result[0].is_watermark is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_position_short_text -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_watermark_detector.py
git commit -m "test: add position+short text watermark rule"
```

### Task 4: Implement position + short text heuristic

**Files:**
- Modify: `core/watermark_detector.py`

**Step 1: Implement rule**

```python
    def _near_edge(self, box, shape):
        h, w = shape
        margin_x = w * 0.1
        margin_y = h * 0.1
        return box.x1 <= margin_x or box.x2 >= w - margin_x or box.y1 <= margin_y or box.y2 >= h - margin_y

    def detect(self, regions, image_shape):
        for r in regions:
            text = (r.source_text or "").lower()
            if any(k in text for k in self.keywords):
                r.is_watermark = True
                r.inpaint_mode = "erase"
                continue
            if r.box_2d and self._near_edge(r.box_2d, image_shape) and len(text) <= 20:
                r.is_watermark = True
                r.inpaint_mode = "erase"
        return regions
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_position_short_text -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/watermark_detector.py
git commit -m "feat: add position+length watermark rule"
```

### Task 5: Add failing test for cross-page repetition

**Files:**
- Modify: `tests/test_watermark_detector.py`

**Step 1: Write failing test**

```python
def test_watermark_detector_cross_page_repeat():
    from core.watermark_detector import WatermarkDetector

    detector = WatermarkDetector()
    regions_page1 = [RegionData(box_2d=Box2D(x1=10, y1=950, x2=120, y2=980), source_text="mangaforfree")]
    regions_page2 = [RegionData(box_2d=Box2D(x1=12, y1=948, x2=122, y2=978), source_text="mangaforfree")]

    detector.detect(regions_page1, image_shape=(1000, 800))
    result = detector.detect(regions_page2, image_shape=(1000, 800))

    assert result[0].is_watermark is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_cross_page_repeat -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_watermark_detector.py
git commit -m "test: add cross-page repetition detection"
```

### Task 6: Implement cross-page repetition rule

**Files:**
- Modify: `core/watermark_detector.py`

**Step 1: Implement repetition tracking**

```python
    def __init__(self, keywords=None):
        self.keywords = set([k.lower() for k in (keywords or [])])
        self._seen = {}

    def _similar_pos(self, box, prev_box, tol=20):
        return abs(box.x1 - prev_box.x1) < tol and abs(box.y1 - prev_box.y1) < tol

    def detect(self, regions, image_shape):
        for r in regions:
            text = (r.source_text or "").lower()
            if text in self._seen and r.box_2d and self._similar_pos(r.box_2d, self._seen[text]):
                r.is_watermark = True
                r.inpaint_mode = "erase"
            if r.box_2d:
                self._seen[text] = r.box_2d
            ...
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_cross_page_repeat -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/watermark_detector.py
git commit -m "feat: add cross-page repetition rule"
```

### Task 7: Add failing tests for integration (skip translation + erase mode)

**Files:**
- Modify: `tests/test_watermark_detector.py`

**Step 1: Write failing tests**

```python
def test_watermark_detector_sets_inpaint_mode():
    from core.watermark_detector import WatermarkDetector

    region = RegionData(box_2d=Box2D(x1=5, y1=950, x2=120, y2=980), source_text="mangaforfree")
    detector = WatermarkDetector()
    result = detector.detect([region], image_shape=(1000, 800))

    assert result[0].inpaint_mode == "erase"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_watermark_detector.py::test_watermark_detector_sets_inpaint_mode -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_watermark_detector.py
git commit -m "test: add inpaint_mode expectation"
```

### Task 8: Integrate detector into OCR/Translation pipeline

**Files:**
- Modify: `core/modules/ocr.py`
- Modify: `core/modules/translator.py`

**Step 1: Integrate detector**

In OCRModule after postprocessor:
```python
from ..watermark_detector import WatermarkDetector
WatermarkDetector().detect(context.regions, image_shape=(h, w))
```

In TranslatorModule skip watermark:
```python
if region.is_watermark:
    continue
```

**Step 2: Run tests**

Run: `pytest tests/test_watermark_detector.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/modules/ocr.py core/modules/translator.py
git commit -m "feat: integrate watermark detector"
```

### Task 9: Full test run

**Step 1: Run tests**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
