# QualityGate Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add QualityGate with automatic retry + fallback (Gemini) for low-quality regions, with bounded budgets and SFX skip.

**Architecture:** Introduce `core/quality_gate.py` to evaluate regions, retry low-score translations with a configurable prompt template, and use fallback model when available. Pipeline calls QualityGate after translation; QualityReport reflects retries and model_used.

**Tech Stack:** Python 3, pytest, pydantic models, YAML config.

### Task 1: Add failing test for retry trigger on low-score region

**Files:**
- Modify: `tests/test_quality_report.py`
- Create: `tests/test_quality_gate.py`

**Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext


def test_quality_gate_retries_low_score_region(monkeypatch):
    from core.quality_gate import QualityGate

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="",  # low quality / empty
        confidence=0.4,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="你好")

    gate = QualityGate()
    gate.apply(ctx, translator)

    assert translator.translate_region.called
    assert ctx.regions[0].target_text == "你好"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_retries_low_score_region -v`
Expected: FAIL (QualityGate not implemented)

**Step 3: Commit**

```bash
git add tests/test_quality_gate.py
git commit -m "test: add quality gate retry expectation"
```

### Task 2: Implement minimal QualityGate with retry

**Files:**
- Create: `core/quality_gate.py`

**Step 1: Write minimal implementation**

```python
class QualityGate:
    def __init__(self):
        pass

    def apply(self, ctx, translator):
        for r in ctx.regions:
            if not r.target_text:
                r.target_text = translator.translate_region(r)
        return ctx
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_retries_low_score_region -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_gate.py
git commit -m "feat: add minimal quality gate"
```

### Task 3: Add failing test for retry budget per image

**Files:**
- Modify: `tests/test_quality_gate.py`

**Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext


def test_quality_gate_respects_image_retry_budget(monkeypatch):
    from core.quality_gate import QualityGate

    regions = [
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="A", target_text="", confidence=0.4),
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="B", target_text="", confidence=0.4),
        RegionData(box_2d=Box2D(x1=0, y1=0, x2=10, y2=10), source_text="C", target_text="", confidence=0.4),
    ]
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=regions)

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="X")

    gate = QualityGate(retry_budget_per_image=2)
    gate.apply(ctx, translator)

    assert translator.translate_region.call_count == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_respects_image_retry_budget -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_quality_gate.py
git commit -m "test: add retry budget expectation"
```

### Task 4: Implement retry budget and per-region retry limit

**Files:**
- Modify: `core/quality_gate.py`

**Step 1: Implement budget logic**

```python
class QualityGate:
    def __init__(self, retry_per_region=1, retry_budget_per_image=2):
        self.retry_per_region = retry_per_region
        self.retry_budget_per_image = retry_budget_per_image

    def apply(self, ctx, translator):
        budget = self.retry_budget_per_image
        for r in ctx.regions:
            if budget <= 0:
                break
            if not r.target_text:
                r.target_text = translator.translate_region(r)
                budget -= 1
        return ctx
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_respects_image_retry_budget -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_gate.py
git commit -m "feat: enforce retry budget"
```

### Task 5: Add failing test for fallback model invocation

**Files:**
- Modify: `tests/test_quality_gate.py`

**Step 1: Write the failing test**

```python
from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext


def test_quality_gate_uses_fallback_when_available(monkeypatch):
    from core.quality_gate import QualityGate

    monkeypatch.setenv("GEMINI_API_KEY", "fake")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="Hello",
        target_text="",
        confidence=0.2,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="bad")
    translator.create_translator = AsyncMock(return_value=translator)

    gate = QualityGate(fallback_model="gemini")
    gate.apply(ctx, translator)

    assert translator.create_translator.called
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_uses_fallback_when_available -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_quality_gate.py
git commit -m "test: add fallback invocation expectation"
```

### Task 6: Implement fallback translator instantiation

**Files:**
- Modify: `core/quality_gate.py`
- Modify: `core/modules/translator.py`

**Step 1: Implement create_translator factory**

In `core/modules/translator.py` add:

```python
    def create_translator(self, model_name: str):
        return AITranslator(model_name=model_name)
```

In `core/quality_gate.py`, call it when fallback needed.

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_uses_fallback_when_available -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_gate.py core/modules/translator.py
git commit -m "feat: create fallback translator"
```

### Task 7: Add failing test for retry prompt template substitution

**Files:**
- Modify: `tests/test_quality_gate.py`

**Step 1: Write failing test**

```python
from core.quality_gate import build_retry_prompt


def test_retry_prompt_template_substitution():
    template = "请将以下文本翻译得更简洁（不超过{max_chars}字）：\n{source_text}\n保留专有名词：{glossary_terms}\n仅输出翻译结果。"
    prompt = build_retry_prompt(template, max_chars=10, source_text="Hello", glossary_terms="A,B")
    assert "10" in prompt
    assert "Hello" in prompt
    assert "A,B" in prompt
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_retry_prompt_template_substitution -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_quality_gate.py
git commit -m "test: add retry prompt template substitution"
```

### Task 8: Implement retry prompt builder

**Files:**
- Modify: `core/quality_gate.py`

**Step 1: Implement build_retry_prompt**

```python
def build_retry_prompt(template: str, **kwargs) -> str:
    return template.format(**kwargs)
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_gate.py::test_retry_prompt_template_substitution -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_gate.py
git commit -m "feat: add retry prompt builder"
```

### Task 9: Add failing test for SFX skip retry

**Files:**
- Modify: `tests/test_quality_gate.py`

**Step 1: Write failing test**

```python
from unittest.mock import AsyncMock

from core.models import Box2D, RegionData, TaskContext


def test_quality_gate_skips_retry_for_sfx():
    from core.quality_gate import QualityGate

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="BANG!",
        target_text="",
        confidence=0.2,
        is_sfx=True,
    )
    ctx = TaskContext(image_path="/tmp/input.png", target_language="zh-CN", regions=[region])

    translator = AsyncMock()
    translator.translate_region = AsyncMock(return_value="boom")

    gate = QualityGate()
    gate.apply(ctx, translator)

    assert translator.translate_region.call_count == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_skips_retry_for_sfx -v`
Expected: FAIL

**Step 3: Commit**

```bash
git add tests/test_quality_gate.py
git commit -m "test: add sfx skip retry"
```

### Task 10: Implement SFX skip retry

**Files:**
- Modify: `core/quality_gate.py`

**Step 1: Implement SFX skip**

```python
    if r.is_sfx:
        continue
```

**Step 2: Run test to verify it passes**

Run: `pytest tests/test_quality_gate.py::test_quality_gate_skips_retry_for_sfx -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/quality_gate.py
git commit -m "feat: skip retry for sfx"
```

### Task 11: Full test run

**Step 1: Run tests**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```
