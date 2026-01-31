# OCR Postprocess Fix Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 修复 OCR 后处理导致的“单字丢失、重叠文本被丢弃、域名水印被提前过滤”问题。

**Architecture:** 在 OCR 后处理层做三处修复：
1) `filter_noise_regions` 在 `relaxed=True` 时不丢弃域名文本；
2) `geometric_cluster_dedup` 对重叠且文本互不包含的 region 进行合并而非丢弃；
3) PaddleOCR 对韩文允许 `min_len=1`，保留单字。

**Tech Stack:** Python 3, pytest.

---

### Task 1: 添加域名文本在 relaxed 模式下保留的测试（失败测试）

**Files:**
- Create: `tests/test_ocr_postprocessing.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData
from core.vision.ocr.postprocessing import filter_noise_regions


def test_filter_noise_regions_keeps_domain_when_relaxed():
    region = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=200, y2=30),
        source_text="NEWTOKI.COM",
        confidence=0.9,
    )

    filtered = filter_noise_regions([region], image_height=2000, relaxed=True)

    assert len(filtered) == 1
    assert filtered[0].source_text == "NEWTOKI.COM"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessing.py::test_filter_noise_regions_keeps_domain_when_relaxed -v`

Expected: FAIL（当前域名在 relaxed 仍被过滤）。

---

### Task 2: 添加重叠文本应合并的测试（失败测试）

**Files:**
- Modify: `tests/test_ocr_postprocessing.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D, RegionData
from core.vision.ocr.postprocessing import geometric_cluster_dedup


def test_geometric_cluster_dedup_merges_overlapping_texts():
    r1 = RegionData(
        box_2d=Box2D(x1=10, y1=10, x2=60, y2=30),
        source_text="그동안",
        confidence=0.9,
    )
    r2 = RegionData(
        box_2d=Box2D(x1=55, y1=12, x2=120, y2=32),
        source_text="일방적으로",
        confidence=0.9,
    )

    merged = geometric_cluster_dedup([r1, r2])

    assert len(merged) == 1
    assert "그동안" in merged[0].source_text
    assert "일방적으로" in merged[0].source_text
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_ocr_postprocessing.py::test_geometric_cluster_dedup_merges_overlapping_texts -v`

Expected: FAIL（当前只保留一个 region）。

---

### Task 3: 实现 OCR 后处理修复

**Files:**
- Modify: `core/vision/ocr/postprocessing.py`

**Step 1: Minimal implementation**

1) 将域名过滤移动到 `if not relaxed` 代码块内：

```python
if not relaxed:
    if re.search(r"\.(com|net|org|io|cn)$", text, re.IGNORECASE):
        continue
```

2) 在 `geometric_cluster_dedup()` 的 cluster 处理里，当文本互不包含时合并：

```python
texts = [t.strip() for t in (r.source_text or "").split() if t.strip()]
unique_texts = list(dict.fromkeys(texts))

if len(unique_texts) <= 1:
    result.append(best)
elif any(a in b for a in unique_texts for b in unique_texts if a != b):
    result.append(best)
else:
    # 按 x1 排序合并
    result.append(merge_group(sorted(cluster, key=lambda r: _box(r).x1)))
```

**Step 2: Run tests**

Run: `pytest tests/test_ocr_postprocessing.py -v`

Expected: PASS。

**Step 3: Commit**

```bash
git add core/vision/ocr/postprocessing.py tests/test_ocr_postprocessing.py
git commit -m "fix: relax watermark/domain filtering and merge overlap text"
```

---

### Task 4: 韩文 min_len=1 的测试与实现

**Files:**
- Create: `tests/test_paddle_engine_min_len.py`
- Modify: `core/vision/ocr/paddle_engine.py`

**Step 1: Write the failing test**

```python
from core.vision.ocr.paddle_engine import _min_len_for_lang


def test_min_len_for_korean_allows_single_char():
    assert _min_len_for_lang("korean", 2) == 1
    assert _min_len_for_lang("ko", 2) == 1
    assert _min_len_for_lang("en", 2) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_paddle_engine_min_len.py::test_min_len_for_korean_allows_single_char -v`

Expected: FAIL（函数不存在）。

**Step 3: Implement minimal code**

```python
# in core/vision/ocr/paddle_engine.py (module level)

def _min_len_for_lang(lang: str, default: int) -> int:
    if (lang or "").lower() in {"korean", "ko"}:
        return 1
    return default
```

并在 `_process_chunk()` 内应用：

```python
min_len = _min_len_for_lang(self.lang, min_len)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_paddle_engine_min_len.py::test_min_len_for_korean_allows_single_char -v`

Expected: PASS。

**Step 5: Commit**

```bash
git add core/vision/ocr/paddle_engine.py tests/test_paddle_engine_min_len.py
git commit -m "fix: allow single-char OCR for korean"
```

---

### Task 5: 全量测试

**Step 1: Run tests**

Run: `pytest -q`

Expected: PASS。

---

Plan complete.
