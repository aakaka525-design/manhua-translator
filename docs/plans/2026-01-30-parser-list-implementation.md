# Parser List Recognition Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add list-page parsing with recognized-site catalog reuse and front-end list selection inside the URL parser view.

**Architecture:** Introduce a generic list parser for unrecognized pages, and a `/api/v1/parser/list` endpoint that recognizes known sites and reuses the scraper catalog rules when possible. The frontend calls list parsing first; when items are returned, it renders a list view with an explicit recognized/unrecognized badge and lets the user manually select items to load chapters.

**Tech Stack:** FastAPI, Pydantic, BeautifulSoup, existing scraper engine, Vue 3 + Pinia.

---

### Task 1: Generic list parser

**Files:**
- Create: `core/parser/list_parser.py`
- Modify: `core/parser/__init__.py`
- Test: `tests/test_list_parser.py`

**Step 1: Write the failing test**

```python
def test_list_parser_extracts_items():
    html = """
    <html><body>
      <a href="/manga/one">
        <img src="/covers/one.jpg" alt="One" />
        <span>One</span>
      </a>
      <a href="/manga/two">
        <img src="/covers/two.jpg" alt="Two" />
        <span>Two</span>
      </a>
    </body></html>
    """
    items = list_parse(html, "https://example.com")
    assert len(items) == 2
    assert items[0]["title"] == "One"
    assert items[0]["url"] == "https://example.com/manga/one"
    assert items[0]["cover_url"] == "https://example.com/covers/one.jpg"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_list_parser.py::test_list_parser_extracts_items -v`
Expected: FAIL (module/function not found)

**Step 3: Write minimal implementation**

```python
def list_parse(html: str, base_url: str) -> list[dict]:
    # BeautifulSoup parse
    # collect anchors with href
    # prefer anchors containing an image
    # derive title from anchor text or img alt
    # normalize url/cover_url with urljoin
    # derive id from last path segment or hash
    # dedupe by normalized url
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_list_parser.py::test_list_parser_extracts_items -v`
Expected: PASS

**Step 5: Commit**

```bash
git add core/parser/list_parser.py core/parser/__init__.py tests/test_list_parser.py
git commit -m "feat: add generic list parser"
```

---

### Task 2: List endpoint (unrecognized fallback)

**Files:**
- Modify: `app/routes/parser.py`
- Test: `tests/test_parser_list_endpoint.py`

**Step 1: Write the failing test**

```python
def test_list_endpoint_unrecognized_uses_generic_parser(monkeypatch):
    html = """
    <html><body>
      <a href="/manga/one"><img src="/covers/one.jpg" alt="One" />One</a>
      <a href="/manga/two"><img src="/covers/two.jpg" alt="Two" />Two</a>
    </body></html>
    """

    from app.main import app
    import app.routes.parser as parser_routes

    monkeypatch.setattr(parser_routes, "fetch_html", lambda *_: html)

    with TestClient(app) as client:
        resp = client.post("/api/v1/parser/list", json={"url": "https://unknown.example/list", "mode": "http"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_type"] == "list"
        assert data["recognized"] is False
        assert data["downloadable"] is False
        assert len(data["items"]) == 2
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_list_endpoint.py::test_list_endpoint_unrecognized_uses_generic_parser -v`
Expected: FAIL (route missing)

**Step 3: Write minimal implementation**

```python
@router.post("/list", response_model=ParserListResponse)
async def parse_list(payload: ParseListRequest):
    html = await anyio.to_thread.run_sync(fetch_html, payload.url, payload.mode)
    items = list_parse(html, _base_url_from_url(payload.url))
    return ParserListResponse(
        page_type="list",
        recognized=False,
        site=None,
        downloadable=False,
        items=items,
        warnings=[],
    )
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_list_endpoint.py::test_list_endpoint_unrecognized_uses_generic_parser -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py tests/test_parser_list_endpoint.py
git commit -m "feat: add parser list endpoint"
```

---

### Task 3: Recognition + catalog URL parsing helpers

**Files:**
- Modify: `app/routes/parser.py`
- Test: `tests/test_parser_list_recognition.py`

**Step 1: Write the failing test**

```python
def test_parse_catalog_url_extracts_path_page_and_orderby():
    from app.routes import parser as parser_routes

    path, page, orderby = parser_routes._parse_catalog_url(
        "https://toongod.org/webtoon/page/2/?m_orderby=views"
    )
    assert path == "/webtoon/"
    assert page == 2
    assert orderby == "views"


def test_recognize_site_matches_known_hosts():
    from app.routes import parser as parser_routes

    site, base_url = parser_routes._recognize_site("https://toongod.org/webtoon/")
    assert site == "toongod"
    assert base_url == "https://toongod.org"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_list_recognition.py::test_parse_catalog_url_extracts_path_page_and_orderby -v`
Expected: FAIL (helpers missing)

**Step 3: Write minimal implementation**

```python
def _recognize_site(url: str) -> tuple[str | None, str | None]:
    # map known hosts to site keys

def _parse_catalog_url(url: str) -> tuple[str | None, int, str | None]:
    # parse path, strip /page/<n>/, read m_orderby
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_list_recognition.py::test_parse_catalog_url_extracts_path_page_and_orderby -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py tests/test_parser_list_recognition.py
git commit -m "feat: add list recognition helpers"
```

---

### Task 4: Recognized list integration with scraper catalog

**Files:**
- Modify: `app/routes/parser.py`
- Test: `tests/test_parser_list_recognized.py`

**Step 1: Write the failing test**

```python
def test_list_endpoint_recognized_returns_downloadable(monkeypatch):
    from app.main import app
    import app.routes.parser as parser_routes

    async def fake_list_recognized(*_args, **_kwargs):
        return [
            {"id": "one", "title": "One", "url": "https://toongod.org/webtoon/one/", "cover_url": None}
        ], []

    monkeypatch.setattr(parser_routes, "_list_recognized_catalog", fake_list_recognized)

    with TestClient(app) as client:
        resp = client.post("/api/v1/parser/list", json={"url": "https://toongod.org/webtoon/"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["recognized"] is True
        assert data["downloadable"] is True
        assert len(data["items"]) == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser_list_recognized.py::test_list_endpoint_recognized_returns_downloadable -v`
Expected: FAIL (helper missing / response mismatch)

**Step 3: Write minimal implementation**

```python
async def _list_recognized_catalog(payload: ParseListRequest, url: str) -> tuple[list[dict], list[str]]:
    # derive base_url, path/page/orderby
    # build ScraperCatalogRequest-like config
    # use _build_engine from app.routes.scraper
    # await engine.list_catalog(...)
    # map Manga -> dict items
```

Update the `/list` endpoint to:
- Call `_recognize_site` and `_list_recognized_catalog` when recognized.
- Set `downloadable=True` when recognized and items exist.
- Add warnings when mapping fails.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_parser_list_recognized.py::test_list_endpoint_recognized_returns_downloadable -v`
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/parser.py tests/test_parser_list_recognized.py
git commit -m "feat: reuse scraper catalog for recognized list"
```

---

### Task 5: Frontend list flow and UI

**Files:**
- Modify: `frontend/src/stores/scraper.js`
- Modify: `frontend/src/views/ScraperView.vue`
- Test: `tests/test_frontend_parser_list_ui.py`

**Step 1: Write the failing test**

```python
def test_frontend_parser_list_endpoint_is_used():
    content = Path("frontend/src/stores/scraper.js").read_text(encoding="utf-8")
    assert "/api/v1/parser/list" in content


def test_frontend_parser_list_badges_present():
    content = Path("frontend/src/views/ScraperView.vue").read_text(encoding="utf-8")
    assert "已识别" in content
    assert "未识别" in content
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_frontend_parser_list_ui.py::test_frontend_parser_list_endpoint_is_used -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Store changes:
- Add `parserApi.list(url, mode, payload)` that POSTs `/api/v1/parser/list`.
- Update the parse action to call list first; if items exist, set `parser.result` to list response; else call `/parse` for detail.

View changes:
- Display a recognition badge ("已识别" / "未识别") when list response is shown.
- Render list items as cards similar to search results.
- On click, call `scraper.selectManga(item)` only if `downloadable=true`.
- Show a hint when `downloadable=false` (list only).

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_frontend_parser_list_ui.py::test_frontend_parser_list_endpoint_is_used -v`
Expected: PASS

**Step 5: Manual check**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

**Step 6: Commit**

```bash
git add frontend/src/stores/scraper.js frontend/src/views/ScraperView.vue tests/test_frontend_parser_list_ui.py
git commit -m "feat: add list parsing flow to URL parser UI"
```

---

### Task 6: README update

**Files:**
- Modify: `README.md`

**Step 1: Update docs**

Add a short section describing `POST /api/v1/parser/list` and example request body.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add parser list endpoint usage"
```

---

Plan complete and saved to `docs/plans/2026-01-30-parser-list-implementation.md`.

Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?
