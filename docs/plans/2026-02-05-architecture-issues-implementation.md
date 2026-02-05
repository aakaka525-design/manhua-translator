# Architecture Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Resolve all P2/P3 items in `ARCHITECTURE_ISSUES.md` by unifying settings/config, deduplicating OCR/translator logic, consolidating scraper/CLI utilities, and cleaning front-end residue while keeping behavior stable.

**Architecture:** Break work into four stages: settings/config; OCR/translator; scraper/CLI; front-end/tooling. Each stage adds small refactors with clear tests and ends by marking completed items in `ARCHITECTURE_ISSUES.md`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic settings, Playwright/httpx, Vue 3 + Vite.

---

### Task 1: Add language update API + .env persistence

**Files:**
- Modify: `app/routes/settings.py`
- Modify: `app/deps.py`
- Create: `app/utils/env_file.py`
- Test: `tests/test_settings_language_update.py` (new)

**Step 1: Write failing test**

```python
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app


def test_settings_language_update_updates_response(tmp_path, monkeypatch):
    # isolate .env
    env_path = tmp_path / ".env"
    env_path.write_text("SOURCE_LANGUAGE=en\nTARGET_LANGUAGE=zh\n", encoding="utf-8")
    monkeypatch.setenv("ENV_FILE", str(env_path))

    client = TestClient(app)

    resp = client.post("/api/v1/settings/language", json={
        "source_language": "ja",
        "target_language": "zh-CN",
    })
    assert resp.status_code == 200

    settings = client.get("/api/v1/settings").json()
    assert settings["source_language"] == "ja"
    assert settings["target_language"] == "zh-CN"

    # persisted to .env
    content = env_path.read_text(encoding="utf-8")
    assert "SOURCE_LANGUAGE=ja" in content
    assert "TARGET_LANGUAGE=zh-CN" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_language_update.py -v`
Expected: FAIL (endpoint and env update helper missing)

**Step 3: Implement minimal code**

```python
# app/utils/env_file.py
from pathlib import Path
import os


def update_env_file(key: str, value: str, env_path: str | None = None) -> None:
    path = Path(env_path or os.getenv("ENV_FILE", ".env"))
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    found = False
    new_lines = []
    for line in lines:
        if not line or line.startswith("#"):
            new_lines.append(line)
            continue
        if line.split("=", 1)[0] == key:
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
```

```python
# app/routes/settings.py
class LanguageUpdateRequest(BaseModel):
    source_language: str
    target_language: str


@router.post("/language")
async def update_language(request: LanguageUpdateRequest, settings=Depends(get_settings)):
    settings.source_language = request.source_language
    settings.target_language = request.target_language
    from app.utils.env_file import update_env_file
    update_env_file("SOURCE_LANGUAGE", request.source_language)
    update_env_file("TARGET_LANGUAGE", request.target_language)
    return {"status": "ok"}
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings_language_update.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/settings.py app/utils/env_file.py app/deps.py tests/test_settings_language_update.py
git commit -m "feat: add language settings update endpoint"
```

---

### Task 2: Lazy binding for translator language + settings usage cleanup

**Files:**
- Modify: `core/modules/translator.py`
- Modify: `app/deps.py`
- Modify: `app/routes/translate.py`
- Test: `tests/test_translator_language_lazy.py` (new)

**Step 1: Write failing test**

```python
from unittest.mock import patch

from core.modules.translator import TranslatorModule
from core.models import TaskContext, RegionData, Box2D


def test_translator_uses_current_settings_language(monkeypatch):
    region = RegionData(
        box_2d=Box2D(x1=0, y1=0, x2=10, y2=10),
        source_text="hello",
        target_text="",
    )
    ctx = TaskContext(task_id="t1", regions=[region])
    translator = TranslatorModule()

    with patch("app.deps.get_settings") as get_settings:
        get_settings.return_value.source_language = "ja"
        get_settings.return_value.target_language = "zh-CN"
        translator._refresh_lang_from_settings()
        assert translator.source_lang == "ja"
        assert translator.target_lang == "zh-CN"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_translator_language_lazy.py -v`
Expected: FAIL (helper missing)

**Step 3: Implement minimal code**

```python
# core/modules/translator.py
    def _refresh_lang_from_settings(self):
        try:
            from app.deps import get_settings
            settings = get_settings()
            self.source_lang = settings.source_language
            self.target_lang = settings.target_language
        except Exception:
            pass

    async def process(self, context: TaskContext) -> TaskContext:
        self._refresh_lang_from_settings()
        ...
```

Also replace any `os.getenv()` usage for API keys or model fields with `get_settings()` where applicable.

**Step 4: Run tests**

Run: `pytest tests/test_translator_language_lazy.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py app/deps.py app/routes/translate.py tests/test_translator_language_lazy.py
git commit -m "refactor: lazy bind translator language to settings"
```

---

### Task 3: Unify model override single channel

**Files:**
- Modify: `app/routes/settings.py`
- Modify: `core/modules/translator.py`
- Test: `tests/test_settings_model_override.py` (new)

**Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app


def test_model_override_does_not_touch_env(monkeypatch):
    client = TestClient(app)
    monkeypatch.delenv("PPIO_MODEL", raising=False)
    resp = client.post("/api/v1/settings/model", json={"model": "foo"})
    assert resp.status_code == 200
    assert "PPIO_MODEL" not in dict(monkeypatch.getenv())
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_model_override.py -v`
Expected: FAIL (env write exists)

**Step 3: Implement minimal code**

- Remove `os.environ['PPIO_MODEL']` update in `set_ai_model`
- Ensure `_get_ai_translator()` uses `get_current_model()` only

**Step 4: Run tests**

Run: `pytest tests/test_settings_model_override.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/settings.py core/modules/translator.py tests/test_settings_model_override.py
git commit -m "refactor: model override single channel"
```

---

### Task 4: Remove dead config + unify model source flag + paddle flags

**Files:**
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `main.py`
- Modify: `Dockerfile.api`
- Test: `tests/test_config_smoke.py` (new)

**Step 1: Write failing test**

```python
from pathlib import Path


def test_model_source_flag_name():
    content = Path("main.py").read_text(encoding="utf-8")
    assert "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK" in content


def test_model_warmup_timeout_removed():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "MODEL_WARMUP_TIMEOUT" not in compose
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_config_smoke.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

- Remove `MODEL_WARMUP_TIMEOUT` from compose + README
- Change `main.py` to use `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK`
- Remove duplicate Paddle flags from compose (keep in Dockerfile)

**Step 4: Run tests**

Run: `pytest tests/test_config_smoke.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add docker-compose.yml README.md main.py Dockerfile.api tests/test_config_smoke.py
git commit -m "chore: clean config flags and dead env vars"
```

---

### Task 5: Create constants + unify edge band ratio

**Files:**
- Create: `core/constants.py`
- Modify: `core/crosspage/crosspage_pairing.py`
- Modify: `core/post_recognition.py`
- Test: `tests/test_edge_band_ratio.py` (new)

**Step 1: Write failing test**

```python
from core import constants


def test_edge_band_ratio_value():
    assert constants.EDGE_BAND_RATIO == 0.12
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_edge_band_ratio.py -v`
Expected: FAIL (constant missing)

**Step 3: Implement minimal code**

```python
# core/constants.py
EDGE_BAND_RATIO = 0.12
```

Update both modules to import `EDGE_BAND_RATIO` and remove hard-coded values.

**Step 4: Run tests**

Run: `pytest tests/test_edge_band_ratio.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/constants.py core/crosspage/crosspage_pairing.py core/post_recognition.py tests/test_edge_band_ratio.py
git commit -m "refactor: unify edge band ratio"
```

---

### Task 6: Unify stderr suppressor

**Files:**
- Create: `core/utils/stderr_suppressor.py`
- Modify: `main.py`
- Modify: `core/pipeline.py`
- Modify: `core/cache.py`
- Test: `tests/test_stderr_suppressor.py` (new)

**Step 1: Write failing test**

```python
from core.utils.stderr_suppressor import suppress_native_stderr


def test_suppress_native_stderr_context_manager():
    with suppress_native_stderr():
        assert True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_stderr_suppressor.py -v`
Expected: FAIL (module missing)

**Step 3: Implement minimal code**

Create a context manager with `SUPPRESS_NATIVE_STDERR` env toggle; replace callers.

**Step 4: Run tests**

Run: `pytest tests/test_stderr_suppressor.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/utils/stderr_suppressor.py main.py core/pipeline.py core/cache.py tests/test_stderr_suppressor.py
git commit -m "refactor: unify stderr suppressor"
```

---

### Task 7: Merge SFX rules into translator + remove wrapper

**Files:**
- Modify: `core/modules/translator.py`
- Modify: `core/ocr/ocr_postprocessor.py`
- Test: `tests/test_translator_sfx.py` (update)

**Step 1: Add test cases for CJK/韩文规则**

```python
# tests/test_translator_sfx.py

def test_sfx_cjk_rules():
    from core.modules.translator import _is_sfx
    assert _is_sfx("カンッ")
    assert _is_sfx("툭")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_translator_sfx.py::test_sfx_cjk_rules -v`
Expected: FAIL

**Step 3: Implement minimal code**

- Move extra CJK/韩文 checks into `translator._is_sfx`
- Remove wrapper logic from `ocr_postprocessor._is_sfx` or import translator version directly

**Step 4: Run tests**

Run: `pytest tests/test_translator_sfx.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/translator.py core/ocr/ocr_postprocessor.py tests/test_translator_sfx.py
git commit -m "refactor: unify sfx rules"
```

---

### Task 8: Consolidate noise filtering

**Files:**
- Modify: `core/ocr/postprocessing.py`
- Modify: `core/modules/translator.py`
- Modify: `core/text_merge/line_merger.py`
- Test: `tests/test_noise_filtering.py` (new)

**Step 1: Write failing test**

```python
from core.ocr.postprocessing import filter_noise_regions
from core.models import RegionData, Box2D


def test_noise_filtering_samples():
    # normal dialogue
    r1 = RegionData(box_2d=Box2D(0,0,10,10), source_text="Hello")
    # sfx
    r2 = RegionData(box_2d=Box2D(0,0,10,10), source_text="BANG!")
    # watermark
    r3 = RegionData(box_2d=Box2D(0,0,10,10), source_text="example.com")
    regions = [r1, r2, r3]
    out = filter_noise_regions(regions)
    assert r1 in out
    assert r3 not in out
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_noise_filtering.py -v`
Expected: FAIL (rules not unified)

**Step 3: Implement minimal code**

- Move relevant text rules from `_is_ocr_noise` into OCR filter
- Reduce `_is_ocr_noise` to semantic-only rules (SFX/罗马数字/轻量)
- Remove `_is_noise_text` from `line_merger.py`

**Step 4: Run tests**

Run: `pytest tests/test_noise_filtering.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/ocr/postprocessing.py core/modules/translator.py core/text_merge/line_merger.py tests/test_noise_filtering.py
git commit -m "refactor: consolidate noise filtering"
```

---

### Task 9: Remove legacy/dead OCR functions

**Files:**
- Modify: `core/ocr/postprocessing.py`
- Modify: `core/vision/paddle_engine.py`
- Modify: `core/modules/translator.py`
- Delete: `core/quality_gate.py`
- Delete: `tests/test_quality_gate.py`
- Test: existing suite

**Step 1: Remove legacy functions**

- Delete `merge_line_regions` (legacy) from `postprocessing.py`
- Delete `recognize_batch` and `detect_and_recognize_roi`
- Delete `merge_adjacent_regions` from `translator.py`
- Delete `core/quality_gate.py` and `tests/test_quality_gate.py`

**Step 2: Run targeted tests**

Run: `pytest tests/test_ocr_postprocessing.py tests/test_paddle_engine_legacy_output.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add core/ocr/postprocessing.py core/vision/paddle_engine.py core/modules/translator.py
git add -u tests/test_quality_gate.py core/quality_gate.py
git commit -m "chore: remove legacy ocr functions"
```

---

### Task 10: Remove unused modules and fix imports

**Files:**
- Delete: `core/vision/image_processor.py`
- Delete: `core/modules/detector.py`
- Delete: `core/ocr_engine.py`
- Modify: `core/vision/__init__.py`, `core/modules/__init__.py`, other import sites
- Test: existing suite

**Step 1: Remove modules + adjust imports**

Search for imports and replace with canonical modules in `core/vision/ocr` and other targets.

**Step 2: Run targeted tests**

Run: `pytest tests/test_ocr_language.py tests/test_watermark_detector.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add -u core/vision/image_processor.py core/modules/detector.py core/ocr_engine.py
# add updated import files
# git add core/vision/__init__.py core/modules/__init__.py ...
git commit -m "chore: remove unused re-export modules"
```

---

### Task 11: Scraper shared URL utils

**Files:**
- Create: `scraper/url_utils.py`
- Modify: `app/routes/scraper.py`
- Modify: `scripts/scraper_cli.py`
- Modify: `scripts/scraper_test.py`
- Modify: `scripts/scraper_gui.py`
- Test: `tests/test_scraper_url_utils.py` (new)

**Step 1: Write failing test**

```python
from scraper.url_utils import infer_id, infer_url


def test_infer_id_url():
    assert infer_id("https://site/123") == "123"
    assert infer_url("123")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper_url_utils.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

Extract shared helpers, update call sites to import from `scraper.url_utils`.

**Step 4: Run tests**

Run: `pytest tests/test_scraper_url_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/url_utils.py app/routes/scraper.py scripts/scraper_cli.py scripts/scraper_test.py scripts/scraper_gui.py tests/test_scraper_url_utils.py
git commit -m "refactor: share scraper url utils"
```

---

### Task 12: Cloudflare challenge utils

**Files:**
- Create: `scraper/challenge.py`
- Modify: `scraper/generic_playwright.py`
- Modify: `scripts/scraper_cli.py`
- Test: `tests/test_scraper_challenge.py` (new)

**Step 1: Write failing test**

```python
from scraper.challenge import looks_like_challenge


def test_cloudflare_marker_lowercase():
    html = "<div>cloudflare ray id</div>"
    assert looks_like_challenge(html)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper_challenge.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

Add `looks_like_challenge()` with `.lower()` and markers, update call sites.

**Step 4: Run tests**

Run: `pytest tests/test_scraper_challenge.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/challenge.py scraper/generic_playwright.py scripts/scraper_cli.py tests/test_scraper_challenge.py
git commit -m "refactor: unify cloudflare detection"
```

---

### Task 13: Cookie parsing unification

**Files:**
- Modify: `scraper/base.py` (or create `scraper/cookies.py`)
- Modify: `app/routes/scraper.py`
- Test: `tests/test_cookie_header_build.py` (new)

**Step 1: Write failing test**

```python
from scraper.base import load_storage_state_cookies
from app.routes.scraper import _build_cookie_header


def test_build_cookie_header_uses_storage_state(tmp_path):
    state = {"cookies": [{"name": "a", "value": "b"}]}
    header = _build_cookie_header(state)
    assert header == "a=b"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cookie_header_build.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

Use `load_storage_state_cookies` in `_build_cookie_header` and format string.

**Step 4: Run tests**

Run: `pytest tests/test_cookie_header_build.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/base.py app/routes/scraper.py tests/test_cookie_header_build.py
git commit -m "refactor: unify cookie parsing"
```

---

### Task 14: Merge parser list into scraper catalog

**Files:**
- Modify: `app/routes/parser.py`
- Modify: `app/routes/scraper.py`
- Modify: `tests/test_parser_list_endpoint.py`
- Test: existing parser list tests

**Step 1: Update tests to call unified endpoint behavior**

```python
# tests/test_parser_list_endpoint.py
# assert parser list uses scraper catalog response shape
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser_list_endpoint.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

- `parse-list` handler should call shared catalog function (or `scraper.catalog`)
- Remove duplicate logic in parser

**Step 4: Run tests**

Run: `pytest tests/test_parser_list_endpoint.py tests/test_parser_list_recognized.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py app/routes/scraper.py tests/test_parser_list_endpoint.py
git commit -m "refactor: merge parser list into scraper catalog"
```

---

### Task 15: Parser HTML fetch uses scraper fetch

**Files:**
- Modify: `app/routes/parser.py`
- Modify: `scraper/*` fetch utilities
- Test: `tests/test_parser_fetch.py` (new)

**Step 1: Write failing test**

```python
def test_parser_fetch_uses_scraper_fetch(mocker):
    mocker.patch("scraper.fetch.fetch_html", return_value="<html></html>")
    # call parser fetch entrypoint and assert fetch_html called
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser_fetch.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

Route parser fetch through scraper fetch utilities.

**Step 4: Run tests**

Run: `pytest tests/test_parser_fetch.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py scraper/* tests/test_parser_fetch.py
git commit -m "refactor: reuse scraper fetch for parser"
```

---

### Task 16: CLI consolidation

**Files:**
- Modify: `main.py`
- Modify: `scripts/cli.py`
- Delete/Modify: `batch_translate.py`
- Test: `tests/test_cli_batch.py` (new)

**Step 1: Write failing test**

```python
import subprocess


def test_main_chapter_subcommand_help():
    result = subprocess.run(["python", "main.py", "chapter", "--help"], capture_output=True, text=True)
    assert result.returncode == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli_batch.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

- Add `chapter` subcommand into `main.py` using existing batch translate logic
- Make `scripts/cli.py` call into main entry or mark as dev tool
- Remove standalone entrypoint in `batch_translate.py`

**Step 4: Run tests**

Run: `pytest tests/test_cli_batch.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add main.py scripts/cli.py batch_translate.py tests/test_cli_batch.py
git commit -m "refactor: consolidate cli entrypoints"
```

---

### Task 17: Frontend serve path + remove residue

**Files:**
- Modify: `main.py`
- Delete: `app/static/js/main.js`
- Delete: `app/static/manifest.json`
- Test: `tests/test_frontend_assets.py` (update)

**Step 1: Update tests**

```python
def test_fastapi_serves_frontend_only_in_dev():
    # assert gating via SERVE_FRONTEND
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_frontend_assets.py -v`
Expected: FAIL

**Step 3: Implement minimal code**

- Add `SERVE_FRONTEND=dev` gate
- Delete residue assets

**Step 4: Run tests**

Run: `pytest tests/test_frontend_assets.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add main.py
git add -u app/static/js/main.js app/static/manifest.json tests/test_frontend_assets.py
git commit -m "chore: gate fastapi frontend and remove residue"
```

---

### Task 18: Move Tk GUI to tools/legacy

**Files:**
- Move: `scripts/scraper_gui.py` -> `tools/scraper_gui.py`
- Create: `tools/README.md`
- Test: N/A (doc-only)

**Step 1: Move file and document**

- Move script
- Add README note: internal/deprecated

**Step 2: Commit**

```bash
git add tools/scraper_gui.py tools/README.md
git add -u scripts/scraper_gui.py
git commit -m "chore: move scraper gui to tools"
```

---

### Task 19: Update ARCHITECTURE_ISSUES.md with completion markers

**Files:**
- Modify: `ARCHITECTURE_ISSUES.md`

**Step 1: Mark completed items per stage**

Add "已完成" markers and brief summaries under each issue.

**Step 2: Commit**

```bash
git add ARCHITECTURE_ISSUES.md
git commit -m "docs: mark architecture issues resolved"
```

---

### Task 20: Full verification

**Step 1: Run full test suite**

Run: `pytest`
Expected: PASS (note baseline failures may exist in other worktrees)

**Step 2: Capture results in summary**

Record any known failures and rationale.

