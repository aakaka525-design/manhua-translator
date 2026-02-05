# OCR Consistency Evaluation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add fixed-box OCR consistency evaluation for upscaled images with normalization and Levenshtein similarity.

**Architecture:** Detect boxes once on original image, map boxes to upscaled image, re-run recognition only, normalize text, compute similarity metrics, output JSON report.

**Tech Stack:** Python, PaddleOCR engine, pytest.

---

### Task 1: Add normalization + similarity unit tests

**Files:**
- Create: `tests/test_ocr_consistency_eval.py`

**Step 1: Write failing tests**

```python
from core.ocr_consistency_eval import normalize_for_compare, levenshtein_ratio


def test_normalize_for_compare_collapses_spaces_and_lowercases():
    text = "  Hello   World\\n"
    assert normalize_for_compare(text) == "hello world"


def test_levenshtein_ratio_basic():
    assert levenshtein_ratio("abc", "abc") == 1.0
    assert levenshtein_ratio("abc", "ab") == 1 - 1/3
```

**Step 2: Run test (expect fail)**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_ocr_consistency_eval.py
```
Expected: FAIL (missing module/functions).

**Step 3: Commit**
```bash
git add tests/test_ocr_consistency_eval.py
git commit -m "test: add ocr consistency eval tests"
```

---

### Task 2: Implement eval helper module

**Files:**
- Create: `core/ocr_consistency_eval.py`

**Step 1: Minimal implementation**

```python
import re


def normalize_for_compare(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"\\s+", " ", text)
    return text.lower()


def levenshtein_ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    la, lb = len(a), len(b)
    if max(la, lb) == 0:
        return 1.0
    dp = list(range(lb + 1))
    for i in range(1, la + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, lb + 1):
            cur = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = cur
    dist = dp[-1]
    return 1 - dist / max(la, lb, 1)
```

**Step 2: Run tests**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_ocr_consistency_eval.py
```
Expected: PASS.

**Step 3: Commit**
```bash
git add core/ocr_consistency_eval.py
git commit -m "feat: add ocr consistency eval helpers"
```

---

### Task 3: Add consistency eval script

**Files:**
- Create: `scripts/ocr_consistency_eval.py`

**Step 1: Write failing test for CLI output path**

```python
import json
from pathlib import Path


def test_consistency_eval_output(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    # just check file creation when invoking main() with mocked OCR
    assert not output.exists()
```

**Step 2: Implement script**
- Use OCR engine detect on original
- Map boxes to upscaled image and recognize
- Normalize + similarity
- Write JSON report

**Step 3: Manual check**

Run:
```
/Users/xa/Desktop/projiect/manhua/.venv/bin/python scripts/ocr_consistency_eval.py \
  --orig /path/to/original.jpg \
  --upscaled /path/to/upscaled.jpg \
  --lang korean \
  --out output/consistency_eval/report.json
```

Expected: report written with summary and samples.

**Step 4: Commit**
```bash
git add scripts/ocr_consistency_eval.py
git commit -m "feat: add ocr consistency eval script"
```

---

### Task 4: Documentation

**Files:**
- Modify: `README.md`

**Step 1: Add usage example**
```bash
python scripts/ocr_consistency_eval.py --orig input.jpg --upscaled output.jpg --lang korean --out output/consistency_eval/report.json
```

**Step 2: Commit**
```bash
git add README.md
git commit -m "docs: add ocr consistency eval usage"
```

