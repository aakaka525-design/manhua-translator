# Status Badge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为前端图片卡片显示翻译状态角标（成功/无文本/失败/处理中/警告），并通过后端提供统一的状态与告警字段。

**Architecture:** 后端在返回章节页面数据时附带 `status` 与 `warning` 信息，前端统一用 `<StatusBadge>` 组件展示并可悬浮/点击查看原因。状态判定基于质量报告（regions/quality_score/recommendations）与翻译文件存在性。

**Tech Stack:** FastAPI (backend), Vue 3 (frontend), JSON quality reports, CSS utilities.

---

### Task 1: 后端状态判定与测试

**Files:**
- Create: `app/services/page_status.py`
- Modify: `app/routes/manga.py`
- Test: `tests/test_page_status.py`

**Step 1: Write the failing test**

```python
# tests/test_page_status.py
from pathlib import Path
import json
from app.services.page_status import compute_page_status


def _write_report(path: Path, regions):
    data = {
        "task_id": "t1",
        "image_path": "data/raw/x/1.jpg",
        "output_path": "output/raw/x/1.jpg",
        "target_language": "zh",
        "timings_ms": {"ocr": 1},
        "regions": regions,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_status_no_text(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(report, [])
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "no_text"


def test_status_warning_retranslate(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(report, [
        {"source_text": "A", "target_text": "B", "quality_score": 0.9, "recommendations": ["retranslate"]}
    ])
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "warning"
    assert status["warning_counts"]["retranslate"] == 1


def test_status_success(tmp_path: Path):
    report = tmp_path / "x__ch1__1__abc.json"
    _write_report(report, [
        {"source_text": "A", "target_text": "B", "quality_score": 0.9, "recommendations": []}
    ])
    status = compute_page_status(
        report_paths=[report],
        translated_exists=True,
        low_quality_threshold=0.7,
        low_quality_ratio=0.3,
    )
    assert status["status"] == "success"
```

**Step 2: Run test to verify it fails**

Run: `./.venv/bin/pytest tests/test_page_status.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.page_status`.

**Step 3: Write minimal implementation**

```python
# app/services/page_status.py
from __future__ import annotations
from pathlib import Path
import json


def _load_latest_report(report_paths: list[Path]) -> dict | None:
    if not report_paths:
        return None
    latest = max(report_paths, key=lambda p: p.stat().st_mtime)
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception:
        return None


def compute_page_status(
    report_paths: list[Path],
    translated_exists: bool,
    low_quality_threshold: float,
    low_quality_ratio: float,
) -> dict:
    # Default
    if not report_paths:
        return {
            "status": "processing",
            "reason": "no_report",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    report = _load_latest_report(report_paths)
    if not report:
        return {
            "status": "processing",
            "reason": "invalid_report",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    regions = report.get("regions") or []
    if len(regions) == 0:
        return {
            "status": "no_text",
            "reason": "regions_empty",
            "warning": False,
            "warning_counts": {"retranslate": 0, "low_quality": 0, "low_ocr": 0},
        }

    # warning aggregation
    retranslate = 0
    low_quality = 0
    low_ocr = 0
    for r in regions:
        recs = r.get("recommendations") or []
        if "retranslate" in recs:
            retranslate += 1
        if (r.get("quality_score") is not None) and r.get("quality_score") < low_quality_threshold:
            low_quality += 1
        if (r.get("confidence") is not None) and r.get("confidence") < 0.6:
            low_ocr += 1

    warn = False
    if retranslate > 0:
        warn = True
    elif regions and (low_quality / max(1, len(regions))) >= low_quality_ratio:
        warn = True

    if warn:
        return {
            "status": "warning",
            "reason": "quality",
            "warning": True,
            "warning_counts": {"retranslate": retranslate, "low_quality": low_quality, "low_ocr": low_ocr},
        }

    return {
        "status": "success" if translated_exists else "processing",
        "reason": "ok" if translated_exists else "no_output",
        "warning": False,
        "warning_counts": {"retranslate": retranslate, "low_quality": low_quality, "low_ocr": low_ocr},
    }
```

**Step 4: Run test to verify it passes**

Run: `./.venv/bin/pytest tests/test_page_status.py -v`
Expected: PASS.

**Step 5: Wire into chapter API**

Modify `app/routes/manga.py` to attach status fields to each page:

```python
# app/routes/manga.py
from app.services.page_status import compute_page_status

# inside loop for p in original_files
report_glob = output_path.parent.parent / "quality_reports"  # output/quality_reports
pattern = f"{manga_id}__{chapter_id}__{p.stem}__*.json"
report_paths = list(report_glob.glob(pattern))
status = compute_page_status(
    report_paths=report_paths,
    translated_exists=translated_file.exists(),
    low_quality_threshold=float(os.getenv("LOW_QUALITY_THRESHOLD", "0.7")),
    low_quality_ratio=float(os.getenv("LOW_QUALITY_RATIO", "0.3")),
)

pages.append({
  "name": p.name,
  "original_url": ...,
  "translated_url": ...,
  "status": status["status"],
  "status_reason": status["reason"],
  "warning_counts": status["warning_counts"],
})
```

**Step 6: Run targeted API test (optional)**

Run: `./.venv/bin/pytest tests/test_page_status.py -v`
Expected: PASS (API not covered yet).

**Step 7: Commit**

```bash
git add app/services/page_status.py app/routes/manga.py tests/test_page_status.py
git commit -m "feat: add page status computation for reader"
```

---

### Task 2: 前端 StatusBadge 组件

**Files:**
- Create: `frontend/src/components/ui/StatusBadge.vue`
- Modify: `frontend/src/views/ReaderView.vue`

**Step 1: Write minimal component**

```vue
<!-- frontend/src/components/ui/StatusBadge.vue -->
<script setup>
const props = defineProps({
  status: { type: String, default: 'processing' },
  reason: { type: String, default: '' },
  warningCounts: { type: Object, default: () => ({}) },
})

const meta = {
  success: { color: 'bg-emerald-500/90', icon: 'fa-check', label: '成功' },
  no_text: { color: 'bg-slate-400/90', icon: 'fa-circle', label: '无文本' },
  failed: { color: 'bg-red-500/90', icon: 'fa-exclamation', label: '失败' },
  processing: { color: 'bg-blue-500/90', icon: 'fa-spinner', label: '处理中', spin: true },
  warning: { color: 'bg-yellow-400/90', icon: 'fa-triangle-exclamation', label: '警告' },
}

const info = computed(() => meta[props.status] || meta.processing)
</script>

<template>
  <div class="px-2 py-1 rounded-full text-[10px] font-semibold text-white shadow flex items-center gap-1"
       :class="info.color"
       :title="reason">
    <i class="fas" :class="[info.icon, info.spin ? 'fa-spin' : '']"></i>
    <span>{{ info.label }}</span>
  </div>
</template>
```

**Step 2: Update ReaderView**

在每个 page 卡片右上角叠加角标：

```vue
<StatusBadge
  class="absolute top-2 right-12 z-20"
  :status="page.status"
  :reason="page.status_reason"
  :warning-counts="page.warning_counts"
/>
```

**Step 3: Commit**

```bash
git add frontend/src/components/ui/StatusBadge.vue frontend/src/views/ReaderView.vue
git commit -m "feat: show translation status badge in reader"
```

---

### Task 3: 配置与文档

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Add env knobs**

```
LOW_QUALITY_THRESHOLD=0.7
LOW_QUALITY_RATIO=0.3
```

**Step 2: Document status legend**

在 README 添加“状态角标说明”，列出 5 种状态与含义。

**Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: add status badge config and legend"
```

---

### Task 4: Final Verification

**Step 1: Run tests**

Run: `./.venv/bin/pytest tests/test_page_status.py -v`
Expected: PASS.

**Step 2: Manual UI check (optional)**

Run: `cd frontend && npm run dev` then open Reader view and verify badge shows per page.

---

Plan complete and saved to `docs/plans/2026-02-01-status-badge-implementation.md`.

Two execution options:
1) Subagent-Driven (this session) — I dispatch per task, review between tasks
2) Parallel Session — new session with executing-plans

Which approach?
