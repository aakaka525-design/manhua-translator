# QualityGate Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add region-level quality scoring and recommendations to QualityReport JSON (record + recommend only).

**Architecture:** Extend `core/quality_report.py` with a small evaluator that computes `quality_score`, `quality_signals`, and ordered `recommendations` per region. Keep pipeline behavior unchanged; only report output is extended.

**Tech Stack:** Python 3, pytest, pydantic models, JSON I/O.

### Task 1: Add failing tests for quality signals and length_fit fallback

**Files:**
- Modify: `tests/test_quality_report.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

from core.metrics import PipelineMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext


def test_quality_report_includes_quality_signals_and_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))

    ctx = TaskContext(
        image_path="/tmp/input.png",
        output_path="/tmp/output.png",
        source_language="en",
        target_language="zh-CN",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
                source_text="Hello",
                target_text="你好",
                confidence=0.8,
            )
        ],
    )

    metrics = PipelineMetrics(total_duration_ms=100)
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())

    region = data["regions"][0]
    assert "quality_score" in region
    assert "quality_signals" in region
    assert region["quality_signals"]["length_fit"] == 0.5
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_quality_report_includes_quality_signals_and_fallback -v`
Expected: FAIL (missing fields or length_fit not present).

**Step 3: Commit**

```bash
git add tests/test_quality_report.py
git commit -m "test: add quality signals expectation"
```

### Task 2: Implement minimal quality evaluation in report writer

**Files:**
- Modify: `core/quality_report.py`

**Step 1: Write minimal implementation**

```python
from typing import Dict, List


def _evaluate_region_quality(region, ctx) -> Dict[str, object]:
    ocr_conf = region.confidence if region.confidence is not None else 0.5
    length_fit = 0.5
    glossary_cov = 1.0
    punctuation_ok = 1.0
    model_conf = 0.5

    score = (
        0.35 * ocr_conf
        + 0.25 * length_fit
        + 0.20 * glossary_cov
        + 0.10 * punctuation_ok
        + 0.10 * model_conf
    )

    return {
        "quality_score": round(score, 4),
        "quality_signals": {
            "ocr_conf": ocr_conf,
            "length_fit": length_fit,
            "glossary_cov": glossary_cov,
            "punctuation_ok": punctuation_ok,
            "model_conf": model_conf,
        },
        "recommendations": [],
    }
```

Hook it in `write_quality_report()` when building each `regions[]` entry.

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_quality_report_includes_quality_signals_and_fallback -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_report.py
git commit -m "feat: add quality signals to quality report"
```

### Task 3: Add failing tests for recommendation triggers and ordering

**Files:**
- Modify: `tests/test_quality_report.py`

**Step 1: Write the failing tests**

```python
import json
from pathlib import Path

from core.metrics import PipelineMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext


def _make_result(tmp_path, monkeypatch, region):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(
        image_path="/tmp/input.png",
        target_language="zh-CN",
        regions=[region],
    )
    metrics = PipelineMetrics(total_duration_ms=100)
    return PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )


def test_quality_report_recommendations_and_order(tmp_path, monkeypatch):
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="H",
        confidence=0.4,
    )

    result = _make_result(tmp_path, monkeypatch, region)

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())
    recs = data["regions"][0]["recommendations"]

    # Expect priority order: retry_translation > low_ocr_confidence > check_overflow > review_glossary
    assert recs[0] == "retry_translation"
    assert "low_ocr_confidence" in recs
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_quality_report_recommendations_and_order -v`
Expected: FAIL (recommendations missing or unordered).

**Step 3: Commit**

```bash
git add tests/test_quality_report.py
git commit -m "test: add recommendation trigger and order expectations"
```

### Task 4: Implement recommendation rules and ordering

**Files:**
- Modify: `core/quality_report.py`

**Step 1: Implement recommendation logic**

```python
    recs: List[str] = []
    if score < 0.55:
        recs.append("retry_translation")
    if ocr_conf < 0.6:
        recs.append("low_ocr_confidence")
    if length_fit < 0.7:
        recs.append("check_overflow")
    if glossary_cov < 0.6:
        recs.append("review_glossary")

    priority = {
        "retry_translation": 0,
        "low_ocr_confidence": 1,
        "check_overflow": 2,
        "review_glossary": 3,
    }
    recs.sort(key=lambda r: priority.get(r, 999))
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_quality_report_recommendations_and_order -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_report.py
git commit -m "feat: add quality recommendations and ordering"
```

### Task 5: Add SFX skip test and logic

**Files:**
- Modify: `tests/test_quality_report.py`
- Modify: `core/quality_report.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

from core.metrics import PipelineMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext


def test_quality_report_skips_glossary_for_sfx(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(
        image_path="/tmp/input.png",
        target_language="zh-CN",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
                source_text="BANG!",
                target_text="砰!",
                confidence=0.8,
                is_sfx=True,
            )
        ],
    )
    metrics = PipelineMetrics(total_duration_ms=100)
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())
    recs = data["regions"][0]["recommendations"]

    assert "review_glossary" not in recs
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_quality_report_skips_glossary_for_sfx -v`
Expected: FAIL

**Step 3: Implement minimal logic**

In `_evaluate_region_quality`, skip adding `review_glossary` when `region.is_sfx` is True.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_quality_report_skips_glossary_for_sfx -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/quality_report.py tests/test_quality_report.py
git commit -m "feat: skip glossary recommendation for sfx"
```

### Task 6: Full test run

**Step 1: Run tests**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -v`
Expected: PASS (note any warnings)

**Step 2: Commit (if needed)**

```bash
git status
```
