# SFX 与混合语言回退修复 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 提升韩文 SFX 识别并修复混合语言残留回退逻辑，同时在调试报告中补充 SFX 相关字段。

**Architecture:** 在 `TranslatorModule._is_sfx` 增加强信号启发式与允许名单，`sfx_dict` 增加必要词库映射；在翻译回退阶段加入 `english_ratio` 判定；在质量报告 debug 模式输出 `normalized_text/is_sfx`。

**Tech Stack:** Python 3.12, pytest, pydantic。

---

### Task 1: 强信号 SFX 识别 + 允许名单

**Files:**
- Modify: `core/sfx_dict.py`
- Modify: `core/modules/translator.py`
- Modify: `core/ocr_postprocessor.py`
- Test: `tests/test_ocr_postprocessor.py`

**Step 1: 写失败测试（短韩文不应误判）**

```python
@pytest.mark.parametrize("text", ["이거", "하지", "뭐야", "네가"])
def test_ocr_postprocessor_short_korean_not_sfx(text):
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text=text,
        confidence=0.9,
    )
    processed = OCRPostProcessor().process_regions([region], lang="korean")
    assert processed[0].is_sfx is False
```

**Step 2: 写失败测试（允许名单 SFX 应命中）**

```python
def test_ocr_postprocessor_marks_custom_korean_sfx():
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="헤이뉴트드",
        confidence=0.9,
    )
    processed = OCRPostProcessor().process_regions([region], lang="korean")
    assert processed[0].is_sfx is True
```

**Step 3: 运行测试确认失败**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_short_korean_not_sfx -v`
Expected: FAIL (目前会被误判或不命中允许名单)

**Step 4: 实现最小代码**

- `core/sfx_dict.py`：新增
```python
KO_SFX_MAP.update({
    "부들": "颤抖",
    "무들": "颤抖",
})

KO_SFX_FORCE = {"헤이뉴트드", "탈간잘자리"}
```

- `core/modules/translator.py`：增强 `_is_sfx`
```python
from ..sfx_dict import KO_SFX_MAP, EN_SFX_MAP, KO_SFX_FORCE

def _hangul_ratio(text: str) -> float:
    if not text:
        return 0.0
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    hangul = sum(1 for c in chars if _HANGUL_RE.match(c))
    return hangul / len(chars)

def _looks_like_hangul_sfx(raw: str) -> bool:
    if not raw:
        return False
    base = _re.sub(r'[!！?？….,。]+$', '', raw).strip()
    if not base or " " in base:
        return False
    if _hangul_ratio(base) < 0.8:
        return False
    length = len(base)
    has_exclaim = bool(_re.search(r'[!！]+$', raw))
    is_repeat = bool(_re.match(r'^([\uac00-\ud7a3]{1,2})\1+$', base))
    if length <= 4:
        return has_exclaim or is_repeat
    if 5 <= length <= 6:
        return is_repeat
    return False

# 在 _is_sfx 里增加：
if base in KO_SFX_FORCE:
    return True
if _looks_like_hangul_sfx(raw):
    return True
```

- `core/ocr_postprocessor.py`：无需改动或仅保留现有逻辑（依赖 `_is_sfx_translator` 覆盖增强）。

**Step 5: 运行测试确认通过**

Run: `pytest tests/test_ocr_postprocessor.py::test_ocr_postprocessor_short_korean_not_sfx -v`
Expected: PASS

**Step 6: 提交**

```bash
git add core/sfx_dict.py core/modules/translator.py tests/test_ocr_postprocessor.py
git commit -m "feat: tighten korean sfx detection with strong signals"
```

---

### Task 2: 混合语言英文残留回退

**Files:**
- Modify: `core/modules/translator.py`
- Test: `tests/test_translator_language_fallback.py`

**Step 1: 写失败测试（英文残留触发回退）**

```python
class _MockMixedAI:
    model = "mock"

    async def translate_batch(self, texts, output_format="numbered", contexts=None):
        return ["O-OR THAT 那个大叔..??"]

    async def translate(self, text):
        return "O-OR THAT 那个大叔..??"


def test_translator_fallback_when_english_ratio_high(monkeypatch):
    translator = TranslatorModule(source_lang="en", target_lang="zh-CN", use_ai=True)
    monkeypatch.setattr(translator, "_get_ai_translator", lambda: _MockMixedAI())
    translator._translator_class = _MockGoogleTranslator

    ctx = TaskContext(image_path="/tmp/in.png", source_language="en", target_language="zh-CN")
    ctx.regions = [
        RegionData(
            box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
            source_text="O-OR THAT AHJUSSI..?!!?",
            confidence=0.9,
        )
    ]

    result = asyncio.run(translator.process(ctx))
    assert result.regions[0].target_text == "中文"
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_translator_language_fallback.py::test_translator_fallback_when_english_ratio_high -v`
Expected: FAIL

**Step 3: 实现最小代码**

在 `core/modules/translator.py` 新增：
```python
def _english_ratio(text: str) -> float:
    if not text:
        return 0.0
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    eng = sum(1 for c in chars if "A" <= c.upper() <= "Z")
    return eng / len(chars)
```

并在回退逻辑中修改：
```python
needs_fallback = (not _has_cjk(translation)) or (_english_ratio(translation) >= 0.35)
# 调用 ai_translator.translate 后再次判断 english_ratio，若仍高则走 Google Translator
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_translator_language_fallback.py::test_translator_fallback_when_english_ratio_high -v`
Expected: PASS

**Step 5: 提交**

```bash
git add core/modules/translator.py tests/test_translator_language_fallback.py
git commit -m "feat: retry when english residue remains"
```

---

### Task 3: 质量报告 debug 输出补齐

**Files:**
- Modify: `core/quality_report.py`
- Test: `tests/test_quality_report.py`

**Step 1: 写失败测试**

```python
def test_quality_report_debug_includes_sfx_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("QUALITY_REPORT_DIR", str(tmp_path))
    monkeypatch.setenv("QUALITY_REPORT_DEBUG", "1")

    ctx = TaskContext(
        image_path="/tmp/input.png",
        target_language="zh-CN",
        regions=[
            RegionData(
                box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
                source_text="부들",
                normalized_text="부들",
                is_sfx=True,
                confidence=0.9,
            )
        ],
    )
    metrics = PipelineMetrics(total_duration_ms=100)
    result = PipelineResult(
        success=True,
        task=ctx,
        processing_time_ms=100,
        stages_completed=["ocr"],
        metrics=metrics.to_dict(),
    )

    report_path = write_quality_report(result)
    data = json.loads(Path(report_path).read_text())
    debug = data["regions"][0]["debug"]
    assert debug["normalized_text"] == "부들"
    assert debug["is_sfx"] is True
```

**Step 2: 运行测试确认失败**

Run: `pytest tests/test_quality_report.py::test_quality_report_debug_includes_sfx_fields -v`
Expected: FAIL

**Step 3: 实现最小代码**

在 `core/quality_report.py` 的 debug dict 中加入：
```python
"normalized_text": getattr(region, "normalized_text", None),
"is_sfx": getattr(region, "is_sfx", False),
```

**Step 4: 运行测试确认通过**

Run: `pytest tests/test_quality_report.py::test_quality_report_debug_includes_sfx_fields -v`
Expected: PASS

**Step 5: 提交**

```bash
git add core/quality_report.py tests/test_quality_report.py
git commit -m "feat: include sfx debug fields in quality report"
```

---

### Task 4: 最小回归测试

**Step 1: 运行新用例集合**

Run:
```bash
/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest \
  tests/test_ocr_postprocessor.py::test_ocr_postprocessor_short_korean_not_sfx \
  tests/test_ocr_postprocessor.py::test_ocr_postprocessor_marks_custom_korean_sfx \
  tests/test_translator_language_fallback.py::test_translator_fallback_when_english_ratio_high \
  tests/test_quality_report.py::test_quality_report_debug_includes_sfx_fields -v
```
Expected: PASS

**Step 2: 如果通过，结束本任务**

```bash
git status
```
