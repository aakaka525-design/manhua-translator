# Quality Report Output Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Write a QualityReport JSON file per processed image, capturing task metadata, stage timings, and region-level outputs.

**Architecture:** Add a small `core/quality_report.py` helper to build and write the report. Integrate it into `Pipeline.process()` after completion (success and failure). Use env overrides for output directory.

**Tech Stack:** Python 3, pytest, pydantic models, JSON I/O.

### Task 1: Add failing test for report writer

**Files:**
- Create: `tests/test_quality_report.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

import pytest

from core.metrics import PipelineMetrics, StageMetrics
from core.models import Box2D, PipelineResult, RegionData, TaskContext


def test_write_quality_report_creates_file(tmp_path, monkeypatch):
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
                confidence=0.9,
            )
        ],
    )

    metrics = PipelineMetrics(total_duration_ms=1234)
    metrics.add_stage(StageMetrics(name="ocr", duration_ms=100, items_processed=1))
    metrics.add_stage(StageMetrics(name="translator", duration_ms=200, items_processed=1))

    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=1234,
        stages_completed=["ocr", "translator"],
        metrics=metrics.to_dict(),
    )

    from core.quality_report import write_quality_report

    report_path = write_quality_report(result)
    assert Path(report_path).exists()

    data = json.loads(Path(report_path).read_text())
    assert data["task_id"] == str(ctx.task_id)
    assert data["image_path"] == ctx.image_path
    assert data["target_language"] == "zh-CN"
    assert "timings_ms" in data
    assert data["regions"][0]["source_text"] == "Hello"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_write_quality_report_creates_file -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError` for `core.quality_report`.

### Task 2: Implement minimal report writer

**Files:**
- Create: `core/quality_report.py`

**Step 3: Write minimal implementation**

```python
import json
import os
from pathlib import Path


def _resolve_output_dir() -> Path:
    env_dir = os.getenv("QUALITY_REPORT_DIR")
    base = Path(env_dir) if env_dir else Path("output") / "quality_reports"
    base.mkdir(parents=True, exist_ok=True)
    return base


def write_quality_report(result) -> str:
    ctx = result.task
    output_dir = _resolve_output_dir()
    report_path = output_dir / f"{ctx.task_id}.json"

    timings = {}
    if isinstance(result.metrics, dict):
        stages = result.metrics.get("stages", [])
        for s in stages:
            timings[s.get("name")] = s.get("duration_ms")
        timings["total"] = result.metrics.get("total_duration_ms")

    data = {
        "task_id": str(ctx.task_id),
        "image_path": ctx.image_path,
        "output_path": ctx.output_path,
        "target_language": ctx.target_language,
        "timings_ms": timings,
        "regions": [
            {
                "region_id": str(r.region_id),
                "source_text": r.source_text,
                "target_text": r.target_text,
                "confidence": r.confidence,
                "box_2d": r.box_2d.model_dump() if r.box_2d else None,
                "quality_score": None,
            }
            for r in (ctx.regions or [])
        ],
    }

    report_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return str(report_path)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_write_quality_report_creates_file -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_quality_report.py core/quality_report.py
git commit -m "feat: add quality report writer"
```

### Task 3: Add failing test for pipeline integration

**Files:**
- Modify: `tests/test_quality_report.py`

**Step 1: Write the failing test**

```python
import asyncio

from core.modules.base import BaseModule
from core.pipeline import Pipeline


class _NoopModule(BaseModule):
    async def process(self, context):
        return context


def test_pipeline_writes_quality_report(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))

    pipeline = Pipeline(
        ocr=_NoopModule(),
        translator=_NoopModule(),
        inpainter=_NoopModule(),
        renderer=_NoopModule(),
    )

    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN")

    result = asyncio.run(pipeline.process(ctx))

    report_path = tmp_path / f"{ctx.task_id}.json"
    assert report_path.exists()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_pipeline_writes_quality_report -v`
Expected: FAIL (report file not created).

### Task 4: Implement pipeline integration

**Files:**
- Modify: `core/pipeline.py`

**Step 3: Write minimal implementation**

```python
from .quality_report import write_quality_report

# After building PipelineResult (success and failure):
try:
    write_quality_report(result)
except Exception:
    logger.exception("Quality report write failed")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_pipeline_writes_quality_report -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/pipeline.py tests/test_quality_report.py
git commit -m "feat: write quality report after pipeline run"
```

### Task 5: Full test run

**Step 1: Run full tests**

Run: `pytest -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
