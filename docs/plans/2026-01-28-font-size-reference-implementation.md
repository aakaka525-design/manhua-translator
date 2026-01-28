# Reference Font Size Anchoring Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Anchor rendered font size to the estimated original size (0.85–1.15x range) with safe fallbacks and telemetry.

**Architecture:** Add a small style config loader, extend `TextRenderer` with a reference-aware fitting helper, and record font size metadata on `RegionData` and in QualityReport. Rendering uses the helper for per-region sizing with controlled relaxation when needed.

**Tech Stack:** Python 3, pytest, Pydantic, PyYAML, Pillow.

### Task 1: Add style config loader + defaults

**Files:**
- Create: `core/style_config.py`
- Create: `config/style.yml`
- Modify: `requirements.txt`
- Test: `tests/test_style_config.py`

**Step 1: Write the failing test**

```python
from pathlib import Path

from core.style_config import load_style_config


def test_style_config_defaults(tmp_path: Path):
    cfg = load_style_config(path=tmp_path / "missing.yml")
    assert cfg.font_size_ref_range == (0.85, 1.15)
    assert cfg.font_size_fallback == (16, 32)
    assert cfg.font_size_relax_min == 12


def test_style_config_overrides(tmp_path: Path):
    path = tmp_path / "style.yml"
    path.write_text(
        "font_size_ref_range: [0.8, 1.2]\n"
        "font_size_fallback: [14, 30]\n"
        "font_size_relax_min: 10\n"
    )
    cfg = load_style_config(path=path)
    assert cfg.font_size_ref_range == (0.8, 1.2)
    assert cfg.font_size_fallback == (14, 30)
    assert cfg.font_size_relax_min == 10
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_style_config.py::test_style_config_defaults -v`  
Expected: FAIL with `ModuleNotFoundError: core.style_config`

**Step 3: Write minimal implementation**

```python
# core/style_config.py
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import yaml


@dataclass(frozen=True)
class StyleConfig:
    font_size_ref_range: Tuple[float, float] = (0.85, 1.15)
    font_size_fallback: Tuple[int, int] = (16, 32)
    font_size_relax_min: int = 12


def _coerce_tuple(value, size, cast):
    if not isinstance(value, (list, tuple)) or len(value) != size:
        return None
    return tuple(cast(v) for v in value)


def load_style_config(path: Optional[Path] = None) -> StyleConfig:
    if path is None:
        path = Path(__file__).resolve().parents[1] / "config" / "style.yml"
    if not path.exists():
        return StyleConfig()
    data = yaml.safe_load(path.read_text()) or {}
    ref_range = _coerce_tuple(data.get("font_size_ref_range"), 2, float)
    fallback = _coerce_tuple(data.get("font_size_fallback"), 2, int)
    relax_min = data.get("font_size_relax_min")
    return StyleConfig(
        font_size_ref_range=ref_range or (0.85, 1.15),
        font_size_fallback=fallback or (16, 32),
        font_size_relax_min=int(relax_min) if relax_min is not None else 12,
    )
```

Add `PyYAML` to `requirements.txt`:

```
PyYAML>=6.0.0
```

Create `config/style.yml`:

```yaml
font_size_ref_range: [0.85, 1.15]
font_size_fallback: [16, 32]
font_size_relax_min: 12
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_style_config.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/style_config.py config/style.yml requirements.txt tests/test_style_config.py
git commit -m "feat: add style config loader for font sizing"
```

### Task 2: Extend RegionData with font size metadata

**Files:**
- Modify: `core/models.py`
- Test: `tests/test_renderer_font_size.py`

**Step 1: Write the failing test**

```python
from core.models import RegionData


def test_region_font_size_metadata_defaults():
    region = RegionData()
    assert region.font_size_ref is None
    assert region.font_size_used is None
    assert region.font_size_relaxed is False
    assert region.font_size_source is None
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer_font_size.py::test_region_font_size_metadata_defaults -v`  
Expected: FAIL (attributes missing)

**Step 3: Write minimal implementation**

```python
# core/models.py (RegionData fields)
    font_size_ref: Optional[int] = Field(default=None, description="Reference font size")
    font_size_used: Optional[int] = Field(default=None, description="Rendered font size")
    font_size_relaxed: bool = Field(default=False, description="Whether font size was relaxed below range")
    font_size_source: Optional[str] = Field(default=None, description="Source of ref size: estimate/override/fallback")
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_renderer_font_size.py::test_region_font_size_metadata_defaults -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/models.py tests/test_renderer_font_size.py
git commit -m "feat: add font size metadata fields to RegionData"
```

### Task 3: Add reference-aware fit helper (range + fallback)

**Files:**
- Modify: `core/renderer.py`
- Test: `tests/test_renderer_font_size.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D
from core.renderer import TextRenderer


def test_fit_text_reference_range():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=200, y2=80)
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text="你好世界",
        box=box,
        ref_size=20,
        ref_source="estimate",
    )
    assert 17 <= size <= 23
    assert meta["font_size_ref"] == 20
    assert meta["font_size_relaxed"] is False


def test_fit_text_reference_fallback():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=200, y2=80)
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text="你好世界",
        box=box,
        ref_size=None,
        ref_source="estimate",
    )
    assert meta["font_size_source"] == "fallback"
    assert 16 <= size <= 32
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer_font_size.py::test_fit_text_reference_range -v`  
Expected: FAIL (method missing)

**Step 3: Write minimal implementation**

```python
# core/renderer.py (imports)
from .style_config import load_style_config

# core/renderer.py (TextRenderer.__init__)
        self.style_config = load_style_config()

# core/renderer.py (new helper)
    def fit_text_to_box_with_reference(
        self,
        text: str,
        box: Box2D,
        ref_size: Optional[int],
        ref_source: str,
        padding: int = 4,
    ):
        cfg = self.style_config
        fallback_min, fallback_max = cfg.font_size_fallback
        ref_min_ratio, ref_max_ratio = cfg.font_size_ref_range
        relax_min = cfg.font_size_relax_min

        if not ref_size or ref_size <= 0:
            min_size, max_size = fallback_min, fallback_max
            source = "fallback"
            ref_value = None
        else:
            min_size = max(relax_min, int(round(ref_size * ref_min_ratio)))
            max_size = max(min_size, int(round(ref_size * ref_max_ratio)))
            source = ref_source
            ref_value = int(ref_size)

        size, lines = self.fit_text_to_box(
            text,
            box,
            min_size=min_size,
            max_size=max_size,
            padding=padding,
        )

        meta = {
            "font_size_ref": ref_value,
            "font_size_source": source,
            "font_size_relaxed": False,
        }
        return size, lines, meta
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_renderer_font_size.py::test_fit_text_reference_range -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/renderer.py tests/test_renderer_font_size.py
git commit -m "feat: add reference-aware font sizing helper"
```

### Task 4: Add relaxation logic for long text

**Files:**
- Modify: `core/renderer.py`
- Test: `tests/test_renderer_font_size.py`

**Step 1: Write the failing test**

```python
from core.models import Box2D
from core.renderer import TextRenderer


def test_fit_text_reference_relaxes_when_needed():
    renderer = TextRenderer()
    box = Box2D(x1=0, y1=0, x2=80, y2=20)
    text = "这是一个非常非常长的文本需要被缩小"
    size, lines, meta = renderer.fit_text_to_box_with_reference(
        text=text,
        box=box,
        ref_size=20,
        ref_source="estimate",
    )
    assert meta["font_size_relaxed"] is True
    assert size < int(round(20 * 0.85))
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer_font_size.py::test_fit_text_reference_relaxes_when_needed -v`  
Expected: FAIL (relaxation not implemented)

**Step 3: Write minimal implementation**

```python
# core/renderer.py inside fit_text_to_box_with_reference
        available_width = box.width - 2 * padding
        available_height = box.height - 2 * padding
        line_height = int(size * self.line_spacing)
        total_height = len(lines) * line_height

        if total_height > available_height:
            meta["font_size_relaxed"] = True
            for sz in range(min_size - 1, relax_min - 1, -1):
                font = self._get_font(sz)
                lines = self.wrap_text(text, font, available_width)
                if len(lines) * int(sz * self.line_spacing) <= available_height:
                    size = sz
                    break
            else:
                size = relax_min
                font = self._get_font(size)
                lines = self.wrap_text(text, font, available_width)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_renderer_font_size.py::test_fit_text_reference_relaxes_when_needed -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/renderer.py tests/test_renderer_font_size.py
git commit -m "feat: relax font size when text cannot fit"
```

### Task 5: Integrate into rendering + quality report

**Files:**
- Modify: `core/renderer.py`
- Modify: `core/quality_report.py`
- Test: `tests/test_renderer_font_size.py`
- Test: `tests/test_quality_report.py`

**Step 1: Write the failing tests**

```python
from pathlib import Path
from PIL import Image

from core.models import Box2D, RegionData
from core.renderer import TextRenderer


def test_renderer_sets_font_size_metadata(tmp_path: Path):
    img_path = tmp_path / "src.png"
    Image.new("RGB", (200, 100), "white").save(img_path)

    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=200, y2=80),
        source_text="你好",
        target_text="你好",
    )
    renderer = TextRenderer()
    renderer._render_sync(
        image_path=str(img_path),
        regions=[region],
        output_path=str(tmp_path / "out.png"),
        original_image_path=str(img_path),
    )

    assert region.font_size_ref is not None
    assert region.font_size_used is not None
    assert region.font_size_source in {"estimate", "override", "fallback"}
```

```python
# tests/test_quality_report.py (add)
def test_quality_report_includes_font_size_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=100, y2=50),
        source_text="Hello",
        target_text="你好",
        confidence=0.8,
        font_size_ref=20,
        font_size_used=18,
        font_size_relaxed=False,
        font_size_source="estimate",
    )
    result = _make_result(tmp_path, monkeypatch, region)
    from core.quality_report import write_quality_report
    data = json.loads(Path(write_quality_report(result)).read_text())
    r = data["regions"][0]
    assert r["font_size_ref"] == 20
    assert r["font_size_used"] == 18
    assert r["font_size_source"] == "estimate"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_renderer_font_size.py::test_renderer_sets_font_size_metadata -v`  
Expected: FAIL (metadata not set)

**Step 3: Write minimal implementation**

```python
# core/renderer.py (_render_sync)
            ref_size = None
            ref_source = "estimate"
            default_font = FontStyleParams().font_size
            if region.font_style_params and region.font_style_params.font_size != default_font:
                ref_size = region.font_style_params.font_size
                ref_source = "override"
            elif region.source_text:
                ref_size = self.style_estimator.estimate_font_size(
                    box, len(region.source_text)
                )
                ref_source = "estimate"

            font_size, lines, meta = self.fit_text_to_box_with_reference(
                text=text,
                box=box,
                ref_size=ref_size,
                ref_source=ref_source,
            )
            region.font_size_ref = meta["font_size_ref"]
            region.font_size_used = font_size
            region.font_size_relaxed = meta["font_size_relaxed"]
            region.font_size_source = meta["font_size_source"]
```

```python
# core/quality_report.py (region dict)
                "font_size_ref": getattr(region, "font_size_ref", None),
                "font_size_used": getattr(region, "font_size_used", None),
                "font_size_relaxed": getattr(region, "font_size_relaxed", None),
                "font_size_source": getattr(region, "font_size_source", None),
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_renderer_font_size.py::test_renderer_sets_font_size_metadata -v`  
Expected: PASS

Run: `pytest tests/test_quality_report.py::test_quality_report_includes_font_size_fields -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/renderer.py core/quality_report.py tests/test_renderer_font_size.py tests/test_quality_report.py
git commit -m "feat: record font size metadata in render and reports"
```

### Task 6: Full test run

**Step 1: Run tests**

Run: `pytest -q`  
Expected: PASS (if `scripts/scraper_test.py` fails due to permissions, document and ask before proceeding)

**Step 2: Commit (if needed)**

```bash
git status
```
