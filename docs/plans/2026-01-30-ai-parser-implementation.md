# AI Parser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a universal URL parser with rule-based extraction plus AI refinement, exposed via API and a scraper subpage.

**Architecture:** Build a two-stage parser (rule_parse → ai_refine), add a new API route, and a UI subpage for URL parsing. Add development logging to a dedicated parser log file.

**Tech Stack:** FastAPI, Python (requests/bs4/readability), Playwright (optional), Vue 3

---

### Task 1: Add parser API skeleton

**Files:**
- Create: `app/routes/parser.py`
- Modify: `app/main.py`

**Step 1: (Skip tests per user request)**
- Note: No test framework currently in place; proceed without tests.

**Step 2: Add new router skeleton**

```py
from fastapi import APIRouter

router = APIRouter(prefix="/parser", tags=["parser"])
```

**Step 3: Register router in `app/main.py`**

```py
from .routes import parser as parser_router
app.include_router(parser_router.router, prefix="/api/v1")
```

**Step 4: Manual check**
- Run: `python main.py server --port 8000`
- Expected: `/api/v1/parser` returns 404 (route exists) but no crash.

---

### Task 2: Rule-based parser

**Files:**
- Create: `core/parser/rule_parser.py`
- Modify: `app/routes/parser.py`

**Step 1: (Skip tests)**

**Step 2: Implement rule_parse()**

```py
def rule_parse(html: str, url: str) -> dict:
    # Extract title, author, date, summary, cover, content_text, paragraphs
    # Prefer JSON-LD and meta tags, fallback to readability heuristic
```

**Step 3: Wire in API**

```py
@router.post("/parse")
async def parse_url(payload: ParseRequest):
    html = fetch_html(payload.url, mode=payload.mode)
    result = rule_parse(html, payload.url)
    return result
```

**Step 4: Manual check**
- POST to `/api/v1/parser/parse` with a public blog URL, expect structured fields.

---

### Task 3: AI refinement

**Files:**
- Create: `core/parser/ai_refiner.py`
- Modify: `app/routes/parser.py`

**Step 1: (Skip tests)**

**Step 2: Implement ai_refine()**

```py
def ai_refine(parsed: dict, snippet: str) -> dict:
    # Fill missing fields only, add confidence and source_map
```

**Step 3: Integrate AI refinement**
- Only call AI when fields are missing or low confidence.
- Add warnings if AI fails (fallback to rule result).

**Step 4: Manual check**
- Use a page with poor metadata and verify fields are filled.

---

### Task 4: Logging

**Files:**
- Modify: `core/logging_config.py`
- Modify: `app/routes/parser.py`

**Step 1: (Skip tests)**

**Step 2: Add `setup_module_logger("parser", "parser.log")`**
- Create parser logger in `core/logging_config.py`

**Step 3: Add logs in API route**
- fetch_start/fetch_end
- rule_parse
- ai_refine

**Step 4: Manual check**
- Verify `logs/YYYYMMDD_parser.log` is created and contains entries.

---

### Task 5: Frontend UI

**Files:**
- Modify: `frontend/src/views/ScraperView.vue`
- Modify: `frontend/src/stores/scraper.js`

**Step 1: (Skip tests)**

**Step 2: Add “URL 解析” subpage**
- Input field + Parse button
- Display title/author/date/summary/cover
- Show paragraphs (first N)
- Buttons: Copy JSON / Copy text

**Step 3: Wire API call**
- Add `parserApi.parse(url)` to store
- Bind results to UI

**Step 4: Manual check**
- Parse a sample article, verify output rendering.

---

### Task 6: Docs update

**Files:**
- Modify: `README.md`

**Step 1: Add usage snippet**
- Mention new URL parser and endpoint.

---

Plan complete and saved to `docs/plans/2026-01-30-ai-parser-implementation.md`.

Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks.
2. **Parallel Session (separate)** - Open new session with executing-plans and batch execution.

Which approach?
