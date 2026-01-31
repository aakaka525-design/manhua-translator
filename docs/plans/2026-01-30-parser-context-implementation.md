# Parser Context Decoupling Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Decouple URL parser actions from left-side scraper settings by deriving a parser context from the input URL and using it for chapter/download actions.

**Architecture:** Add a parser-specific context in the Pinia store (base_url/host/recognized/downloadable/site) and use it to build payloads for chapter/download calls. Update the parser UI to show the derived site and route list actions through the parser context. Leave existing search/catalog flows unchanged.

**Tech Stack:** Vue 3, Pinia, FastAPI (existing endpoints), pytest (string-based frontend checks).

---

### Task 1: Add parser context helpers in store

**Files:**
- Modify: `frontend/src/stores/scraper.js`
- Create: `tests/test_frontend_parser_context_store.py`

**Step 1: Write the failing test**

```python
from pathlib import Path


def test_parser_context_helpers_present():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "selectMangaFromParser" in content
    assert "parser.context" in content or "context:" in content
    assert "proxyParserImageUrl" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parser_context_helpers_present -v`
Expected: FAIL (helpers not found)

**Step 3: Write minimal implementation**

Add in `frontend/src/stores/scraper.js`:
- `parser.context` default fields: `baseUrl`, `host`, `site`, `recognized`, `downloadable`
- `getParserDefaults(site)` returning default `storage_state_path`/`user_data_dir`
- `deriveParserContext(url, listResult)` updates `parser.context` (use `new URL(url)`)
- `getParserPayload()` using parser context (no left-panel values)
- `proxyParserImageUrl(url)` using parser context for `/api/v1/scraper/image`
- `selectMangaFromParser(manga)` to call `api.chapters` with parser payload

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parser_context_helpers_present -v`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/stores/scraper.js tests/test_frontend_parser_context_store.py
git commit -m "feat: add parser context helpers"
```

---

### Task 2: Wire parseUrl to set parser context

**Files:**
- Modify: `frontend/src/stores/scraper.js`
- Modify: `tests/test_frontend_parser_context_store.py`

**Step 1: Write the failing test**

```python
def test_parse_url_sets_context():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "deriveParserContext" in content
    assert "parser.context" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parse_url_sets_context -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- In `parseUrl`, call `deriveParserContext(url, listResult)` after list call (and before detail fallback).
- Reset parser context on invalid URL.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parse_url_sets_context -v`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/stores/scraper.js tests/test_frontend_parser_context_store.py
git commit -m "feat: derive parser context from URL"
```

---

### Task 3: Use parser context for chapter/download actions

**Files:**
- Modify: `frontend/src/stores/scraper.js`
- Modify: `tests/test_frontend_parser_context_store.py`

**Step 1: Write the failing test**

```python
def test_parser_download_uses_context():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "selectedMangaSource" in content
    assert "getActivePayload" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parser_download_uses_context -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Add `selectedMangaSource` (default `"scraper"`).
- In `selectManga`, set source to `"scraper"`.
- In `selectMangaFromParser`, set source to `"parser"`.
- Add `getActivePayload()` and use it in `startDownload`/`downloadSelected`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_parser_context_store.py::test_parser_download_uses_context -v`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/stores/scraper.js tests/test_frontend_parser_context_store.py
git commit -m "feat: route downloads via parser context"
```

---

### Task 4: Update parser UI for derived site context

**Files:**
- Modify: `frontend/src/views/ScraperView.vue`
- Modify: `tests/test_frontend_parser_list_ui.py`

**Step 1: Write the failing test**

```python
def test_frontend_parser_context_label_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "解析站点" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_parser_list_ui.py::test_frontend_parser_context_label_present -v`
Expected: FAIL

**Step 3: Write minimal implementation**

- Show `解析站点：<host>` using `scraper.parser.context.host`.
- Change list card click to `scraper.selectMangaFromParser(item)`.
- For list covers, call `scraper.proxyParserImageUrl(item.cover_url)`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_parser_list_ui.py::test_frontend_parser_context_label_present -v`
Expected: PASS

**Step 5: Manual check**

Run: `cd frontend && npm run build`
Expected: Build succeeds

**Step 6: Commit**

```bash
git add frontend/src/views/ScraperView.vue tests/test_frontend_parser_list_ui.py
git commit -m "feat: decouple parser UI context"
```

---

Plan complete and saved to `docs/plans/2026-01-30-parser-context-implementation.md`.

Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
