# OCRPostProcessor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an OCRPostProcessor that normalizes OCR text, flags SFX, and integrates into OCRModule with Korean OCR correction rules and cached regex patterns.

**Architecture:** Introduce `core/ocr_postprocessor.py` with deterministic `process_regions()` and cached regexes. Extend `RegionData` with `normalized_text` and `is_sfx`. Reuse existing `core/modules/translator.py::_is_sfx` where possible and extend with CJK/Korean patterns. Apply Korean OCR fixes only when lang is Korean. Call the postprocessor in `core/modules/ocr.py` after OCR detection.

**Tech Stack:** Python 3, pydantic models, pytest.

### Task 1: Add failing test for normalization + model fields

**Files:**
- Create: `tests/test_ocr_postprocessor.py`
- Modify: `core/models.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData


def test_ocr_postprocessor_normalizes_text():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="  Hello   World\n",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor

    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].normalized_text == "Hello World"
    assert processed[0].source_text == "  Hello   World\n"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_normalizes_text -v`
Expected: FAIL with `ModuleNotFoundError` for `core.ocr_postprocessor` or missing field on `RegionData`.

**Step 3: Implement minimal model fields + OCRPostProcessor**

- Update `core/models.py` to add:
  - `normalized_text: Optional[str] = None`
  - `is_sfx: bool = False`

- Create `core/ocr_postprocessor.py` with cached regexes:

```python
import re
from typing import List

from .models import RegionData


class OCRPostProcessor:
    _WS_RE = re.compile(r"\s+")

    def _normalize(self, text: str) -> str:
        if not text:
            return ""
        return self._WS_RE.sub(" ", text).strip()

    def _is_sfx(self, text: str) -> bool:
        return False

    def _fix_korean(self, text: str) -> str:
        return text

    def process_regions(self, regions: List[RegionData], lang: str = "en") -> List[RegionData]:
        for r in regions:
            if r.source_text:
                normalized = self._normalize(r.source_text)
                if lang in {"korean", "ko"}:
                    normalized = self._fix_korean(normalized)
                r.normalized_text = normalized
                r.is_sfx = self._is_sfx(r.normalized_text)
            else:
                r.normalized_text = ""
                r.is_sfx = False
        return regions
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_normalizes_text -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/models.py core/ocr_postprocessor.py tests/test_ocr_postprocessor.py
git commit -m "feat: add OCR postprocessor and model fields"
```

### Task 2: Add failing test for Korean OCR correction

**Files:**
- Modify: `tests/test_ocr_postprocessor.py`

**Step 1: Write the failing test**

```python
def test_ocr_postprocessor_korean_corrections():
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="이닌 억은",
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="korean")

    assert processed[0].normalized_text == "이번 역은"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_korean_corrections -v`
Expected: FAIL (no correction yet).

**Step 3: Implement minimal Korean fixes**

In `OCRPostProcessor`, add cached regex replacements:

```python
    _KO_FIXES = [
        (re.compile(r"이닌"), "이번"),
        (re.compile(r"억은"), "역은"),
    ]

    def _fix_korean(self, text: str) -> str:
        out = text
        for pattern, repl in self._KO_FIXES:
            out = pattern.sub(repl, out)
        return out
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_korean_corrections -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/ocr_postprocessor.py tests/test_ocr_postprocessor.py
git commit -m "feat: add korean OCR correction rules"
```

### Task 3: Add failing test for SFX detection (expanded)

**Files:**
- Modify: `tests/test_ocr_postprocessor.py`

**Step 1: Write the failing test**

```python
import pytest


@pytest.mark.parametrize("text", [
    "BANG!",
    "砰！",
    "咔嚓",
    "ドキドキ",
    "쾅!",
])
def test_ocr_postprocessor_marks_sfx(text):
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=text,
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].is_sfx is True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_marks_sfx -v`
Expected: FAIL if SFX logic not implemented.

**Step 3: Minimal implementation**

In `OCRPostProcessor`, reuse translator._is_sfx and extend with cached regexes:

```python
from core.modules.translator import _is_sfx as _is_sfx_translator

class OCRPostProcessor:
    _SFX_CJK_RE = re.compile(r"^[\u4e00-\u9fff]{1,6}[!！]?$")
    _SFX_JP_RE = re.compile(r"^[\u3040-\u30ff]{2,8}[!！]?$")
    _SFX_KO_RE = re.compile(r"^[\uac00-\ud7a3]{1,6}[!！]?$")

    def _is_sfx(self, text: str) -> bool:
        if not text:
            return False
        if _is_sfx_translator(text):
            return True
        t = text.strip()
        if self._SFX_CJK_RE.match(t):
            return True
        if self._SFX_JP_RE.match(t):
            return True
        if self._SFX_KO_RE.match(t):
            return True
        return False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_marks_sfx -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ocr_postprocessor.py core/ocr_postprocessor.py
git commit -m "feat: expand sfx detection in OCR postprocessor"
```

### Task 4: Add edge case parameterized tests

**Files:**
- Modify: `tests/test_ocr_postprocessor.py`

**Step 1: Write the failing test**

```python
import pytest


@pytest.mark.parametrize(
    "text, expected_norm, expected_sfx",
    [
        ("", "", False),
        ("   ", "", False),
        ("...", "...", False),
        ("!!!", "!!!", True),
        ("LONG   TEXT   HERE", "LONG TEXT HERE", False),
    ],
)
def test_ocr_postprocessor_edge_cases(text, expected_norm, expected_sfx):
    from core.models import Box2D, RegionData
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=text,
        confidence=0.9,
    )

    from core.ocr_postprocessor import OCRPostProcessor
    processed = OCRPostProcessor().process_regions([region], lang="en")

    assert processed[0].normalized_text == expected_norm
    assert processed[0].is_sfx is expected_sfx
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_edge_cases -v`
Expected: FAIL if behavior mismatches.

**Step 3: Minimal implementation**

Adjust normalization/SFX logic if any case fails.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_edge_cases -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_ocr_postprocessor.py core/ocr_postprocessor.py
git commit -m "test: add OCR postprocessor edge cases"
```

### Task 5: Add failing test for OCRModule integration (AsyncMock)

**Files:**
- Modify: `tests/test_ocr_postprocessor.py`
- Modify: `core/modules/ocr.py`

**Step 1: Write the failing test**

```python
import asyncio
from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext
from core.modules.ocr import OCRModule


def test_ocr_module_applies_postprocessor():
    module = OCRModule(use_mock=True)
    module.engine.lang = "en"
    module.engine.detect_and_recognize = AsyncMock(return_value=[
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="  Hello  ",
            confidence=0.9,
        )
    ])

    ctx = TaskContext(image_path="/tmp/input.png")
    result = asyncio.run(module.process(ctx))

    assert result.regions[0].normalized_text == "Hello"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_module_applies_postprocessor -v`
Expected: FAIL (normalized_text missing).

**Step 3: Implement minimal integration**

In `core/modules/ocr.py`, after `context.regions = await self.engine.detect_and_recognize(...)`, add:

```python
from ..ocr_postprocessor import OCRPostProcessor

OCRPostProcessor().process_regions(context.regions, lang=target_lang)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_module_applies_postprocessor -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/ocr.py tests/test_ocr_postprocessor.py
git commit -m "feat: run OCR postprocessor in OCR module"
```

### Task 6: Full test run

**Step 1: Run tests**

Run: `pytest -v`
Expected: PASS (if scraper_test permissions remain a blocker, document failure).

**Step 2: Commit (if needed)**

```bash
git status
```
