# Local Fonts and Icons Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Serve fonts and icons from local bundled assets to avoid HTTP public-IP PNA/CORS blocks.

**Architecture:** Remove external CDN links from `frontend/index.html`. Add local font and icon packages via npm and import their CSS in the frontend entry so Vite bundles them into same-origin assets.

**Tech Stack:** Vite, Vue 3, @fontsource/*, @fortawesome/fontawesome-free, pytest.

---

### Task 1: Add failing tests for external assets

**Files:**
- Create: `tests/test_frontend_assets.py`

**Step 1: Write the failing tests**

```python
from pathlib import Path


def test_frontend_index_has_no_external_css():
    content = Path("frontend/index.html").read_text(encoding="utf-8")
    assert "fonts.googleapis.com" not in content
    assert "cdnjs.cloudflare.com" not in content


def test_frontend_entry_imports_local_fonts_and_icons():
    content = Path("frontend/src/main.js").read_text(encoding="utf-8")
    assert "@fontsource/bangers" in content
    assert "@fontsource/bebas-neue" in content
    assert "@fontsource/inter" in content
    assert "@fontsource/space-grotesk" in content
    assert "@fortawesome/fontawesome-free/css/all.css" in content
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_frontend_assets.py::test_frontend_index_has_no_external_css -v`
Expected: FAIL (external CDN links still present)

Run: `pytest tests/test_frontend_assets.py::test_frontend_entry_imports_local_fonts_and_icons -v`
Expected: FAIL (imports missing)

---

### Task 2: Remove external CDN links

**Files:**
- Modify: `frontend/index.html`

**Step 1: Implement minimal change**

Remove the `<link>` tags for Google Fonts and Font Awesome CDN from `frontend/index.html`.

**Step 2: Run the index test**

Run: `pytest tests/test_frontend_assets.py::test_frontend_index_has_no_external_css -v`
Expected: PASS

---

### Task 3: Add local font and icon packages

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/main.js`

**Step 1: Implement minimal change**

Add dependencies:
- `@fontsource/bangers`
- `@fontsource/bebas-neue`
- `@fontsource/inter`
- `@fontsource/space-grotesk`
- `@fortawesome/fontawesome-free`

Import the CSS in `frontend/src/main.js`:

```js
import '@fontsource/bangers';
import '@fontsource/bebas-neue';
import '@fontsource/inter';
import '@fontsource/space-grotesk';
import '@fortawesome/fontawesome-free/css/all.css';
```

**Step 2: Install dependencies**

Run: `npm install` (in `frontend/`)

**Step 3: Run the import test**

Run: `pytest tests/test_frontend_assets.py::test_frontend_entry_imports_local_fonts_and_icons -v`
Expected: PASS

---

### Task 4: Verify full test suite (optional)

**Step 1: Run full pytest**

Run: `pytest`
Expected: FAIL in `tests/test_renderer_font_size.py::test_fit_text_reference_wraps_long_text_when_min_size_too_large` (pre-existing)

---

### Task 5: Commit

**Step 1: Commit (only if user requests)**

```bash
git add tests/test_frontend_assets.py frontend/index.html frontend/package.json frontend/src/main.js frontend/package-lock.json
git commit -m "chore: localize frontend fonts and icons"
```
