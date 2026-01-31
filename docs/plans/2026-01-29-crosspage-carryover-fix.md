# Crosspage Carryover Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ensure跨页“next_top”不会因缺失 CarryOver 而空白，并默认在 Pipeline 里挂载 CarryOver Store，同时在质量报告中输出跨页标识便于排查。

**Architecture:** OCR 仍标记 next_top/current_bottom；Translator 只在 CarryOver 命中时跳过翻译，否则回退正常翻译。Pipeline 初始化时创建 CarryOver Store（可用环境变量覆盖路径）。质量报告增加 crosspage_pair_id/crosspage_role 字段作为可观测性。

**Tech Stack:** Python 3, pytest.

### Task 1: next_top 缺失 CarryOver 时回退翻译（TDD）

**Files:**
- Modify: `tests/test_crosspage_context.py`
- Modify: `core/modules/translator.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule


def test_next_top_falls_back_without_carryover():
    module = TranslatorModule(use_mock=True, use_ai=False)
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="당했던",
        crosspage_role="next_top",
        crosspage_pair_id="pair-1",
        skip_translation=True,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    result = asyncio.run(module.process(ctx))

    assert result.regions[0].target_text == "[翻译] 당했던"
    assert result.regions[0].skip_translation is False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_next_top_falls_back_without_carryover -v`  
Expected: FAIL (target_text 为空或 `[INPAINT_ONLY]`)

**Step 3: Implement minimal fix**

```python
# core/modules/translator.py
if getattr(r, "crosspage_role", None) == "next_top":
    store = getattr(self, "_carryover_store", None)
    if store and getattr(r, "crosspage_pair_id", None):
        carried = store.consume(r.crosspage_pair_id)
        if carried:
            r.target_text = carried
            r.skip_translation = True
        else:
            r.skip_translation = False
    else:
        r.skip_translation = False
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_next_top_falls_back_without_carryover -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py tests/test_crosspage_context.py
git commit -m "fix: fallback translate when carryover missing"
```

### Task 2: Pipeline 默认挂载 CarryOver Store（TDD）

**Files:**
- Create: `tests/test_pipeline_carryover.py`
- Modify: `core/pipeline.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from core.pipeline import Pipeline
from core.modules.base import BaseModule
from core.modules.translator import TranslatorModule
from core.crosspage_carryover import CrosspageCarryOverStore


class _NoopModule(BaseModule):
    async def process(self, context):
        return context


def test_pipeline_wires_carryover_store(tmp_path, monkeypatch):
    carry_path = tmp_path / "carryover.jsonl"
    monkeypatch.setenv("CROSSPAGE_CARRYOVER_PATH", str(carry_path))

    pipeline = Pipeline(
        ocr=_NoopModule(),
        translator=TranslatorModule(use_mock=True, use_ai=False),
        inpainter=_NoopModule(),
        renderer=_NoopModule(),
    )

    store = getattr(pipeline.translator, "_carryover_store", None)
    assert isinstance(store, CrosspageCarryOverStore)
    assert store.path == carry_path
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_pipeline_carryover.py::test_pipeline_wires_carryover_store -v`  
Expected: FAIL (store 为 None)

**Step 3: Implement minimal wiring**

```python
# core/pipeline.py (in __init__)
from pathlib import Path
from .crosspage_carryover import CrosspageCarryOverStore

carry_path = os.getenv("CROSSPAGE_CARRYOVER_PATH")
if not carry_path:
    base = Path(os.getenv("QUALITY_REPORT_DIR", "output/quality_reports"))
    carry_path = str(base / "_carryover.jsonl")
self.translator._carryover_store = CrosspageCarryOverStore(Path(carry_path))
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_pipeline_carryover.py::test_pipeline_wires_carryover_store -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/pipeline.py tests/test_pipeline_carryover.py
git commit -m "feat: wire crosspage carryover store in pipeline"
```

### Task 3: 质量报告输出跨页标识（TDD）

**Files:**
- Modify: `tests/test_quality_report.py`
- Modify: `core/quality_report.py`

**Step 1: Write the failing test**

```python
def test_quality_report_includes_crosspage_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="당했던",
        target_text="受过的",
        crosspage_pair_id="pair-1",
        crosspage_role="next_top",
    )
    result = _make_result(tmp_path, monkeypatch, region)
    from core.quality_report import write_quality_report
    data = json.loads(Path(write_quality_report(result)).read_text())
    r = data["regions"][0]
    assert r["crosspage_pair_id"] == "pair-1"
    assert r["crosspage_role"] == "next_top"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_report.py::test_quality_report_includes_crosspage_fields -v`  
Expected: FAIL (字段缺失)

**Step 3: Implement minimal fields**

```python
# core/quality_report.py in regions dict
"crosspage_pair_id": getattr(region, "crosspage_pair_id", None),
"crosspage_role": getattr(region, "crosspage_role", None),
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_quality_report.py::test_quality_report_includes_crosspage_fields -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/quality_report.py tests/test_quality_report.py
git commit -m "feat: report crosspage identifiers"
```

### Task 4: Targeted test run

**Step 1: Run tests**

Run: `pytest tests/test_crosspage_context.py::test_next_top_falls_back_without_carryover -v`  
Run: `pytest tests/test_pipeline_carryover.py::test_pipeline_wires_carryover_store -v`  
Run: `pytest tests/test_quality_report.py::test_quality_report_includes_crosspage_fields -v`

**Step 2: Optional full run**

Run: `pytest -v` (if time allows)
