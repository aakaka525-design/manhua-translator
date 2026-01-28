# Quality Report Naming With Source Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Include source slug (series/chapter/page) in quality report filenames while keeping task_id for uniqueness.

**Architecture:** Add a small slug builder in `core/quality_report.py` that derives a safe filename component from `TaskContext.image_path`, then use it when writing the report. Update tests to validate naming.

**Tech Stack:** Python 3, pytest.

### Task 1: Add failing test for source-based filename

**Files:**
- Modify: `tests/test_quality_report.py`

**Step 1: Write the failing test**

```python
def test_quality_report_filename_includes_source(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    ctx = TaskContext(
        image_path="data/raw/demo-manga/ch-1/01.jpg",
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
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=10,
        stages_completed=["ocr"],
        metrics=PipelineMetrics(total_duration_ms=10).to_dict(),
    )
    from core.quality_report import write_quality_report
    report_path = write_quality_report(result)
    name = Path(report_path).name
    assert "demo-manga__ch-1__01" in name
    assert str(ctx.task_id) in name
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_quality_report_filename_includes_source -v`  
Expected: FAIL (filename is just `<task_id>.json`)

**Step 3: Commit (none yet)**

### Task 2: Implement source slug in filename

**Files:**
- Modify: `core/quality_report.py`

**Step 1: Write minimal implementation**

```python
import re

def _sanitize_component(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "_", text)
    text = text.strip("_")
    return text or "unknown"


def _source_slug(image_path: str) -> str:
    p = Path(image_path)
    parts = list(p.parts)
    rel_parts = []
    if "data" in parts:
        idx = parts.index("data")
        if idx + 1 < len(parts) and parts[idx + 1] == "raw":
            rel_parts = parts[idx + 2 :]
        else:
            rel_parts = parts[idx + 1 :]
    if not rel_parts:
        rel_parts = parts[-3:]
    if len(rel_parts) > 3:
        rel_parts = rel_parts[-3:]
    if rel_parts:
        rel_parts[-1] = Path(rel_parts[-1]).stem
    slug = "__".join(_sanitize_component(x) for x in rel_parts if x)
    if len(slug) > 120:
        slug = slug[-120:]
    return slug or _sanitize_component(p.stem)
```

Then update `write_quality_report`:

```python
slug = _source_slug(ctx.image_path)
report_path = output_dir / f"{slug}__{ctx.task_id}.json"
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_quality_report_filename_includes_source -v`  
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_report.py tests/test_quality_report.py
git commit -m "feat: include source slug in quality report filename"
```

### Task 3: Full test run

**Step 1: Run tests**

Run: `pytest -q`  
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
