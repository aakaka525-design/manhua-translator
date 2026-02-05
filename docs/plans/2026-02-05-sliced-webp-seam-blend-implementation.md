# Sliced WebP Seam Blend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate visible seams in sliced WebP output by enabling lossless slice saving and adding CSS gradient blending in the reader.

**Architecture:** Backend adds a slice-only lossless switch at save time; frontend detects `*_slices.json` and renders slices with overlap feathering in the translated layer, including compare-mode support and fallback when JSON fails.

**Tech Stack:** Python (PIL, OpenCV), Vue 3 (Vite), Tailwind CSS.

---

### Task 0: Add frontend test framework (Vitest + Vue Test Utils)

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/vitest.config.js`
- Create: `frontend/tests/setup.js`
- Create: `frontend/tests/smoke.test.js`

**Step 1: Write a failing smoke test**

Create `frontend/tests/smoke.test.js`:
```js
import { describe, it, expect } from "vitest";

describe("vitest", () => {
  it("runs", () => {
    expect(1).toBe(2);
  });
});
```

**Step 2: Run test to verify it fails**

Run:
```bash
cd frontend
npm test -- --run tests/smoke.test.js
```
Expected: **FAIL** (missing test script / vitest not installed).

**Step 3: Add Vitest + Vue Test Utils + jsdom**

Update `frontend/package.json`:
- Add devDependencies: `vitest`, `@vue/test-utils`, `jsdom`
- Add script:
```json
"test": "vitest run"
```

Run:
```bash
cd frontend
npm install
```

**Step 4: Add Vitest config + setup**

Create `frontend/vitest.config.js`:
```js
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: "./tests/setup.js"
  }
});
```

Create `frontend/tests/setup.js`:
```js
import { afterEach } from "vitest";

afterEach(() => {
  document.body.innerHTML = "";
});
```

**Step 5: Update smoke test to pass**

Update `frontend/tests/smoke.test.js`:
```js
import { describe, it, expect } from "vitest";

describe("vitest", () => {
  it("runs", () => {
    expect(1).toBe(1);
  });
});
```

**Step 6: Run test to verify it passes**

Run:
```bash
cd frontend
npm test -- --run tests/smoke.test.js
```
Expected: **PASS**

**Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vitest.config.js frontend/tests/setup.js frontend/tests/smoke.test.js
git commit -m "chore: add vitest setup for frontend"
```

### Task 1: Add a failing backend test for lossless slice saving

**Files:**
- Modify: `tests/test_image_io.py`

**Step 1: Write the failing test**

```python
def test_save_image_webp_slices_lossless_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_FORMAT", "webp")
    monkeypatch.setenv("WEBP_SLICES_LOSSLESS", "1")
    arr = np.zeros((20000, 10, 3), dtype=np.uint8)

    import core.image_io as image_io

    calls = []

    def _spy(self, fp, format=None, **kwargs):
        Path(fp).write_bytes(b"")
        calls.append((format, kwargs))

    monkeypatch.setattr(image_io.Image.Image, "save", _spy, raising=False)

    saved = save_image(arr, str(tmp_path / "out.png"), purpose="final")
    assert saved.endswith("_slices.json")
    assert calls, "expected at least one slice save"
    fmt, kwargs = calls[0]
    assert fmt == "WEBP"
    assert kwargs.get("lossless") is True
    assert "quality" not in kwargs
```

**Step 2: Run test to verify it fails**

Run:
```bash
MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_image_io.py::test_save_image_webp_slices_lossless_env
```
Expected: **FAIL** (lossless not applied).

---

### Task 2: Implement slice-only lossless option + docs

**Files:**
- Modify: `core/image_io.py`
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Implement env flag in slice saving**

Add helper in `core/image_io.py`:
```python
def _webp_slices_lossless() -> bool:
    return os.getenv("WEBP_SLICES_LOSSLESS", "0") == "1"
```

Update `_save_webp_slices`:
```python
if _webp_slices_lossless():
    crop.save(path, format="WEBP", lossless=True)
else:
    crop.save(path, format="WEBP", quality=int(os.getenv("WEBP_QUALITY_FINAL", "90")))
```

**Step 2: Document env var**

Add to `.env.example`:
```
WEBP_SLICES_LOSSLESS=0
```
Add a short note to `README.md` under output format section.

**Step 3: Run test to verify it passes**

Run:
```bash
MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_image_io.py::test_save_image_webp_slices_lossless_env
```
Expected: **PASS**

**Step 4: Commit**
```bash
git add core/image_io.py tests/test_image_io.py .env.example README.md
git commit -m "feat: add lossless option for webp slices"
```

---

### Task 3: Frontend slice renderer + CSS blend (with Vitest tests)

**Files:**
- Create: `frontend/src/utils/slice_index.js`
- Create: `frontend/src/components/ui/SlicedImage.vue`
- Create: `frontend/tests/slice_index.test.js`
- Create: `frontend/tests/SlicedImage.test.js`
- Modify: `frontend/src/components/ui/CompareSlider.vue`

**Step 1: Write failing tests (utils + component missing)**

Create `frontend/tests/slice_index.test.js`:
```js
import { describe, it, expect } from "vitest";
import { isSliceIndex, sliceBaseDir, sliceFallback } from "../src/utils/slice_index.js";

describe("slice_index", () => {
  it("detects and derives slice paths", () => {
    expect(isSliceIndex("/output/1_slices.json")).toBe(true);
    expect(isSliceIndex("/output/1.webp")).toBe(false);
    expect(sliceBaseDir("/output/1_slices.json")).toBe("/output/1_slices/");
    expect(sliceFallback("/output/1_slices.json")).toBe("/output/1.webp");
  });
});
```

Create `frontend/tests/SlicedImage.test.js`:
```js
import { describe, it, expect, vi } from "vitest";
import { mount } from "@vue/test-utils";
import SlicedImage from "../src/components/ui/SlicedImage.vue";

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("SlicedImage", () => {
  it("renders slices when index loads", async () => {
    const payload = {
      version: 1,
      original_width: 800,
      original_height: 1200,
      slice_height: 600,
      overlap: 12,
      slices: [
        { file: "slice_000.webp", y: 0, height: 600 },
        { file: "slice_001.webp", y: 588, height: 600 }
      ]
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve(payload)
    });

    const wrapper = mount(SlicedImage, {
      props: { src: "/output/1_slices.json" }
    });

    await flush();
    await flush();

    const imgs = wrapper.findAll("img");
    expect(imgs.length).toBe(2);
    expect(imgs[0].attributes("src")).toBe("/output/1_slices/slice_000.webp");
    expect(imgs[1].attributes("src")).toBe("/output/1_slices/slice_001.webp");
    expect(imgs[1].attributes("style")).toContain("margin-top: -12px");
  });

  it("falls back to webp then original on error", async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error("nope"));

    const wrapper = mount(SlicedImage, {
      props: {
        src: "/output/1_slices.json",
        fallbackOriginal: "/output/1.png"
      }
    });

    await flush();

    const img = wrapper.find("img");
    expect(img.attributes("src")).toBe("/output/1.webp");

    await img.trigger("error");
    await flush();

    expect(wrapper.find("img").attributes("src")).toBe("/output/1.png");
  });
});
```

**Step 2: Run tests to verify they fail**

Run:
```bash
cd frontend
npm test -- --run tests/slice_index.test.js tests/SlicedImage.test.js
```
Expected: **FAIL** (missing module/components).

**Step 3: Implement utils + sliced renderer**

Create `frontend/src/utils/slice_index.js`:
```js
export function isSliceIndex(url) {
  return typeof url === "string" && url.endsWith("_slices.json");
}
export function sliceBaseDir(url) {
  return url.replace("_slices.json", "_slices/");
}
export function sliceFallback(url) {
  return url.replace("_slices.json", ".webp");
}
```

Create `frontend/src/components/ui/SlicedImage.vue` to:
- Fetch slice JSON when `src` ends with `_slices.json`.
- Build slice URLs with `sliceBaseDir`.
- Render slice `<img>` list with overlap blending:
  - `margin-top: -overlapPx`
  - `mask-image` + `-webkit-mask-image` linear-gradient.
- On JSON failure, switch to fallback `.webp`, then to `fallbackOriginal` on error.

Modify `CompareSlider.vue`:
- Use `SlicedImage` for translated layer.
- Pass `fallback-original` prop (use `original` URL).
- Keep original overlay `<img>` unchanged.

**Step 4: Run tests to verify they pass**

Run:
```bash
cd frontend
npm test -- --run tests/slice_index.test.js tests/SlicedImage.test.js
```
Expected: **PASS**

**Step 5: Manual verification**
- Load reader with a sliced page and compare mode on/off.
- Confirm no seam in overlap zone.
- Simulate JSON 404 and confirm fallback to `.webp`, then original.

**Step 6: Commit**
```bash
git add frontend/src/utils/slice_index.js frontend/src/components/ui/SlicedImage.vue frontend/src/components/ui/CompareSlider.vue frontend/tests/slice_index.test.js frontend/tests/SlicedImage.test.js
git commit -m "feat: render sliced webp with overlap blending"
```

---

### Task 4: End-to-end validation

**Files:**
- None (runtime only)

**Step 1: Run a real-page flow**
Run:
```bash
OUTPUT_FORMAT=webp WEBP_SLICES_LOSSLESS=1 \\
MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python main.py image \\
/Users/xa/Desktop/projiect/manhua/data/raw/sexy-woman/chapter-1/1.jpg \\
--output output/ncnn_slice_test
```

**Step 2: Verify output**
- Ensure `*_slices.json` exists and slices render without seams.
- Verify compare slider works.

**Step 3: Commit (if any runtime docs/notes needed)**
Only if artifacts are committed (otherwise skip).

---

# Execution Handoff

Plan complete and saved to `docs/plans/2026-02-05-sliced-webp-seam-blend-implementation.md`. Two execution options:

1. **Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration  
2. **Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints  

Which approach?
