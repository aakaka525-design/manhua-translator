# Architecture Issues Remaining Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 完成 `ARCHITECTURE_ISSUES.md` 中剩余 3 项（normalize_base_url 复用、解析请求模型合并、GUI slugify 复用）。

**Architecture:** 以最小改动复用已有 helper 与模型，新增小型单元测试保障复用约束，保持行为不变。

**Tech Stack:** Python, FastAPI, Pydantic, pytest

### Task 1: 复用 normalize_base_url（parser/scraper）

**Files:**
- Modify: `app/routes/parser.py`
- Modify: `app/routes/scraper.py`
- Create: `tests/test_routes_normalize_base_url.py`

**Step 1: Write the failing test**

```python
from app.routes import parser as parser_routes
from app.routes import scraper as scraper_routes
from scraper import url_utils


def test_routes_normalize_base_url_reuses_helper():
    assert parser_routes._normalize_base_url is url_utils.normalize_base_url
    assert scraper_routes._normalize_base_url is url_utils.normalize_base_url
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_routes_normalize_base_url.py -v`
Expected: FAIL with assertion error (local function is not shared helper)

**Step 3: Write minimal implementation**

- In `app/routes/parser.py`, replace local `_normalize_base_url` with import:
  - `from scraper.url_utils import normalize_base_url as _normalize_base_url`
  - remove local `_normalize_base_url` function
- In `app/routes/scraper.py`, add import:
  - `from scraper.url_utils import normalize_base_url as _normalize_base_url`
  - remove local `_normalize_base_url` function

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_routes_normalize_base_url.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py app/routes/scraper.py tests/test_routes_normalize_base_url.py
git commit -m "refactor: reuse normalize_base_url helper"
```

### Task 2: 合并 ParseRequest 与 ParseListRequest

**Files:**
- Modify: `app/routes/parser.py`
- Create: `tests/test_parser_models.py`

**Step 1: Write the failing test**

```python
from app.routes import parser as parser_routes


def test_parse_list_request_reuses_parse_request():
    assert parser_routes.ParseListRequest is parser_routes.ParseRequest
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_models.py -v`
Expected: FAIL with assertion error (distinct classes)

**Step 3: Write minimal implementation**

- In `app/routes/parser.py`, remove `ParseListRequest` class and alias:

```python
class ParseRequest(BaseModel):
    url: str
    mode: str = "http"

ParseListRequest = ParseRequest
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_models.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py tests/test_parser_models.py
git commit -m "refactor: reuse parse request model"
```

### Task 3: 复用 slugify_keyword（GUI）

**Files:**
- Modify: `scraper/url_utils.py`
- Modify: `tools/scraper_gui.py`
- Modify: `tests/test_scraper_url_utils.py`

**Step 1: Write the failing test**

```python
from scraper.url_utils import slugify_keyword


def test_slugify_keyword():
    assert slugify_keyword("  My_Keyword!! ") == "my-keyword"
    assert slugify_keyword("A  B--C") == "a-b-c"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_scraper_url_utils.py -v`
Expected: FAIL with ImportError/AttributeError (slugify_keyword missing)

**Step 3: Write minimal implementation**

- Add to `scraper/url_utils.py`:

```python
def slugify_keyword(keyword: str) -> str:
    value = keyword.strip().lower().replace("_", " ")
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s\-]+", "-", value)
    return value.strip("-")
```

- In `tools/scraper_gui.py`, remove local `_slugify_keyword` and import:
  - `from scraper.url_utils import slugify_keyword as _slugify_keyword`

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_scraper_url_utils.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add scraper/url_utils.py tools/scraper_gui.py tests/test_scraper_url_utils.py
git commit -m "refactor: reuse slugify keyword helper"
```

### Task 4: 更新 ARCHITECTURE_ISSUES 标记

**Files:**
- Modify: `ARCHITECTURE_ISSUES.md`

**Step 1: Update checklist**

- 标记以下项为已完成并补充简短摘要：
  - 路由 `_normalize_base_url` 复用
  - `ParseRequest` 与 `ParseListRequest` 合并/复用
  - `tools/scraper_gui.py` 复用 slugify helper

**Step 2: Commit**

```bash
git add ARCHITECTURE_ISSUES.md
git commit -m "docs: close remaining architecture issues"
```
