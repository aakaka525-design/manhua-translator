# Crosspage CarryOver Translation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement cross-page carryover translation with JSON top/bottom output so split bubbles render on both pages without residual text.

**Architecture:** Add a carryover store keyed by crosspage pair_id, persist to JSONL for resumability, and extend OCR/Translator to generate pair IDs and two-part translations. Parsing uses strict JSON with fallback.

**Tech Stack:** Python 3, pydantic models, pytest.

---

### Task 1: Add carryover store tests (fail first)

**Files:**
- Create: `core/crosspage_carryover.py`
- Create: `tests/test_crosspage_carryover.py`

**Step 1: Write the failing test**

```python
import json
from pathlib import Path

from core.crosspage_carryover import CrosspageCarryOverStore


def test_carryover_store_persist_and_consume(tmp_path):
    store_path = tmp_path / "_carryover.jsonl"
    store = CrosspageCarryOverStore(store_path)

    store.put(pair_id="p1", bottom_text="B", from_page="3.jpg", to_page="4.jpg")
    assert store.get("p1") == "B"

    # Persist to disk
    store.flush()
    data = [json.loads(line) for line in store_path.read_text().splitlines()]
    assert data[0]["pair_id"] == "p1"
    assert data[0]["bottom_text"] == "B"

    # Consume clears entry
    assert store.consume("p1") == "B"
    assert store.get("p1") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_carryover.py::test_carryover_store_persist_and_consume -v`
Expected: FAIL (ModuleNotFoundError or missing implementation)

**Step 3: Write minimal implementation**

Create `core/crosspage_carryover.py`:

```python
import json
import time
from pathlib import Path


class CrosspageCarryOverStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._data = {}

    def put(self, pair_id: str, bottom_text: str, from_page: str, to_page: str):
        self._data[pair_id] = {
            "pair_id": pair_id,
            "bottom_text": bottom_text,
            "from_page": from_page,
            "to_page": to_page,
            "created_at": time.time(),
            "status": "pending",
        }

    def get(self, pair_id: str):
        item = self._data.get(pair_id)
        return item["bottom_text"] if item else None

    def consume(self, pair_id: str):
        item = self._data.pop(pair_id, None)
        if not item:
            return None
        return item["bottom_text"]

    def flush(self):
        if not self._data:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            for item in self._data.values():
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_carryover.py::test_carryover_store_persist_and_consume -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/crosspage_carryover.py tests/test_crosspage_carryover.py
git commit -m "feat: add crosspage carryover store"
```

---

### Task 2: Add pair_id computation in OCR (fail first)

**Files:**
- Modify: `core/modules/ocr.py`
- Modify: `core/models.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

Add test in `tests/test_crosspage_context.py`:

```python
def test_crosspage_pair_id_assigned(tmp_path, monkeypatch):
    from core.modules.ocr import OCRModule

    class _FakeEngine:
        lang = "korean"

        async def detect_and_recognize(self, image_path: str):
            from core.models import Box2D, RegionData
            return [
                RegionData(box_2d=Box2D(x1=0, y1=90, x2=50, y2=100), source_text="AAA")
            ]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            from core.models import Box2D, RegionData
            if edge == "top":
                return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=50, y2=10), source_text="BBB")]
            return []

    module = OCRModule(use_mock=True)
    module.engine = _FakeEngine()

    # Create fake next page file
    (tmp_path / "1.jpg").write_bytes(b"x")
    (tmp_path / "2.jpg").write_bytes(b"x")

    from core.models import TaskContext
    ctx = TaskContext(image_path=str(tmp_path / "1.jpg"), source_language="korean")

    result = __import__("asyncio").run(module.process(ctx))
    assert result.regions[0].crosspage_pair_id is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_crosspage_pair_id_assigned -v`
Expected: FAIL (attribute missing or None)

**Step 3: Write minimal implementation**

- Add to `core/models.py`:
  - `crosspage_pair_id: Optional[str] = None`
  - `crosspage_role: Optional[str] = None`

- In `core/modules/ocr.py`, when matching `current_bottom` ↔ `next_top`, compute `pair_id` and set:
  - `cur.crosspage_pair_id = pair_id; cur.crosspage_role = "current_bottom"`
  - `nxt.crosspage_pair_id = pair_id; nxt.crosspage_role = "next_top"`

Use a stable fingerprint like:

```python
import hashlib

def _pair_id_for_regions(bottom, top):
    key = f"{round(bottom.edge_box_2d.x1)}:{round(bottom.edge_box_2d.y1)}:{(top.source_text or '').lower()}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()[:12]
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_crosspage_pair_id_assigned -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/ocr.py core/models.py tests/test_crosspage_context.py
git commit -m "feat: assign crosspage pair id"
```

---

### Task 3: JSON split parsing for top/bottom (fail first)

**Files:**
- Modify: `core/modules/translator.py`
- Create: `core/translation_splitter.py`
- Test: `tests/test_translation_splitter.py`

**Step 1: Write the failing test**

```python
from core.translation_splitter import parse_top_bottom


def test_parse_top_bottom_json():
    text = '{"top":"Hello","bottom":"World"}'
    top, bottom = parse_top_bottom(text)
    assert top == "Hello"
    assert bottom == "World"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_translation_splitter.py::test_parse_top_bottom_json -v`
Expected: FAIL (ModuleNotFoundError)

**Step 3: Write minimal implementation**

Create `core/translation_splitter.py`:

```python
import json


def parse_top_bottom(text: str):
    data = json.loads(text)
    top = data.get("top", "").strip()
    bottom = data.get("bottom", "").strip()
    return top, bottom
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_translation_splitter.py::test_parse_top_bottom_json -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/translation_splitter.py tests/test_translation_splitter.py

git commit -m "feat: parse top/bottom json"
```

---

### Task 4: Translator uses carryover store (fail first)

**Files:**
- Modify: `core/modules/translator.py`
- Modify: `core/pipeline.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
import asyncio

from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule
from core.crosspage_carryover import CrosspageCarryOverStore


def test_translator_writes_carryover(tmp_path):
    store = CrosspageCarryOverStore(tmp_path / "_carryover.jsonl")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=90, x2=50, y2=100),
        source_text="AAA",
        crosspage_texts=["BBB"],
        crosspage_pair_id="p1",
        crosspage_role="current_bottom",
    )

    module = TranslatorModule(use_ai=False, use_mock=True)
    module._carryover_store = store

    ctx = TaskContext(image_path="/tmp/1.jpg", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert store.get("p1") is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_translator_writes_carryover -v`
Expected: FAIL (attribute missing / store unused)

**Step 3: Write minimal implementation**

- Add optional `carryover_store` in TranslatorModule (set by Pipeline)
- When region has `crosspage_pair_id` and `crosspage_role == "current_bottom"`, format prompt for JSON and parse top/bottom. Write bottom to store; assign top to region.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_translator_writes_carryover -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py core/pipeline.py tests/test_crosspage_context.py

git commit -m "feat: carryover store integration"
```

---

### Task 5: Next page consumes carryover (fail first)

**Files:**
- Modify: `core/modules/translator.py`
- Test: `tests/test_crosspage_context.py`

**Step 1: Write the failing test**

```python
import asyncio
from core.models import Box2D, RegionData, TaskContext
from core.modules.translator import TranslatorModule
from core.crosspage_carryover import CrosspageCarryOverStore


def test_translator_consumes_carryover(tmp_path):
    store = CrosspageCarryOverStore(tmp_path / "_carryover.jsonl")
    store.put(pair_id="p1", bottom_text="BOTTOM", from_page="1.jpg", to_page="2.jpg")

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=50, y2=10),
        source_text="BBB",
        crosspage_pair_id="p1",
        crosspage_role="next_top",
    )

    module = TranslatorModule(use_ai=False, use_mock=True)
    module._carryover_store = store

    ctx = TaskContext(image_path="/tmp/2.jpg", target_language="zh-CN", regions=[region])
    asyncio.run(module.process(ctx))

    assert region.target_text == "BOTTOM"
    assert store.get("p1") is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_translator_consumes_carryover -v`
Expected: FAIL

**Step 3: Write minimal implementation**

If `crosspage_role == "next_top"` and store has entry, fill `target_text` and set `skip_translation=True`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_translator_consumes_carryover -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py tests/test_crosspage_context.py

git commit -m "feat: consume carryover on next page"
```

---

### Task 6: End-to-end mock OCR test (He/llo)

**Files:**
- Modify: `tests/test_crosspage_context.py`

**Step 1: Write failing test**

```python
import asyncio
from pathlib import Path

from core.models import Box2D, RegionData, TaskContext
from core.pipeline import Pipeline


def test_crosspage_end_to_end_mock_ocr(tmp_path):
    # Build fake pages
    (tmp_path / "1.jpg").write_bytes(b"x")
    (tmp_path / "2.jpg").write_bytes(b"x")

    class _MockOCR:
        lang = "en"
        async def detect_and_recognize(self, image_path: str):
            if image_path.endswith("1.jpg"):
                return [RegionData(box_2d=Box2D(x1=0, y1=90, x2=50, y2=100), source_text="He")]
            return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=50, y2=10), source_text="llo")]

        async def detect_and_recognize_band(self, image_path: str, edge: str, band_height: int):
            if image_path.endswith("2.jpg") and edge == "top":
                return [RegionData(box_2d=Box2D(x1=0, y1=0, x2=50, y2=10), source_text="llo")]
            return []

    pipeline = Pipeline()
    pipeline.ocr.engine = _MockOCR()
    pipeline.translator.use_mock = True

    ctx1 = TaskContext(image_path=str(tmp_path / "1.jpg"), source_language="en", target_language="en")
    ctx2 = TaskContext(image_path=str(tmp_path / "2.jpg"), source_language="en", target_language="en")

    asyncio.run(pipeline.process(ctx1))
    asyncio.run(pipeline.process(ctx2))

    assert ctx1.regions[0].target_text
    assert ctx2.regions[0].target_text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_crosspage_context.py::test_crosspage_end_to_end_mock_ocr -v`
Expected: FAIL

**Step 3: Implement minimal logic needed**

Wire pipeline to keep carryover store across process calls.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_crosspage_context.py::test_crosspage_end_to_end_mock_ocr -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_crosspage_context.py core/pipeline.py core/modules/translator.py core/modules/ocr.py

git commit -m "test: add end-to-end mock OCR crosspage"
```

---

### Task 7: Full test run

**Step 1: Run tests**

Run: `pytest tests/test_crosspage_context.py -v`
Expected: PASS

**Step 2: Commit (if needed)**

```bash
git status
```

---

Plan complete and saved to `docs/plans/2026-01-29-crosspage-carryover-implementation.md`.

Two execution options:

1. Subagent-Driven (this session)
2. Parallel Session (separate, use executing-plans)

Which approach?
