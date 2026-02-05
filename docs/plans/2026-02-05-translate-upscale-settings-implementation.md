# Translate + Upscale Runtime Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add minimal runtime settings for translation model, upscale model, and upscale scale with local persistence + backend in-memory overrides.

**Architecture:** Frontend settings store keeps local state (localStorage). Backend exposes a small settings API that stores in-memory overrides, which the translator and upscaler read at runtime. No persistent server-side settings store.

**Tech Stack:** FastAPI (Python), Vue 3 + Pinia, Vitest

---

### Task 1: Backend settings API + overrides

**Files:**
- Modify: `app/routes/settings.py`
- Modify: `core/modules/upscaler.py`
- Create: `tests/test_settings_upscale_endpoint.py`

**Step 1: Write the failing tests**

```python
from fastapi.testclient import TestClient


def test_settings_upscale_update():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/settings/upscale", json={"model": "realesr-animevideov3-x4", "scale": 4})
        assert resp.status_code == 200

        get_resp = client.get("/api/v1/settings")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["upscale_model"] == "realesr-animevideov3-x4"
        assert data["upscale_scale"] == 4


def test_settings_upscale_validation():
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/settings/upscale", json={"model": "bad-model", "scale": 4})
        assert resp.status_code == 422

        resp = client.post("/api/v1/settings/upscale", json={"model": "realesr-animevideov3-x4", "scale": 3})
        assert resp.status_code == 422
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings_upscale_endpoint.py -q`  
Expected: FAIL (endpoint not found / missing fields)

**Step 3: Implement minimal backend**

- In `app/routes/settings.py`:
  - Add module-level overrides: `_upscale_model_override`, `_upscale_scale_override`.
  - Extend `SettingsResponse` with `upscale_model: str` and `upscale_scale: int`.
  - Add `UpscaleUpdateRequest` model with `model: str`, `scale: int`.
  - Add allowlist, e.g.
    ```python
    _UPSCALE_MODELS = {
        "realesrgan-x4plus-anime",
        "realesrgan-x4plus",
        "realesr-animevideov3-x4",
    }
    ```
  - Add `POST /api/v1/settings/upscale`:
    - Validate model in allowlist
    - Validate scale in {2, 4}
    - Set overrides
    - Return confirmation
  - Add helper getters:
    - `get_current_upscale_model()`
    - `get_current_upscale_scale()`

- In `core/modules/upscaler.py`:
  - Add helper functions to read overrides first:
    ```python
    def _override_upscale_model():
        try:
            from app.routes.settings import get_current_upscale_model
            return get_current_upscale_model()
        except Exception:
            return None
    ```
  - Use override in `_run_ncnn` and `_run_pytorch` when resolving model/scale.

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_settings_upscale_endpoint.py -q`  
Expected: PASS

**Step 5: Commit**

```bash
git add app/routes/settings.py core/modules/upscaler.py tests/test_settings_upscale_endpoint.py
git commit -m "feat: add upscale runtime settings"
```

---

### Task 2: Frontend settings store + tests

**Files:**
- Modify: `frontend/src/stores/settings.js`
- Create: `frontend/tests/settings.test.js`

**Step 1: Write the failing tests**

```javascript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useSettingsStore } from "@/stores/settings";

beforeEach(() => {
  setActivePinia(createPinia());
  vi.stubGlobal("fetch", vi.fn());
  localStorage.clear();
});

it("updates upscale settings and calls API", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
  const store = useSettingsStore();
  await store.selectUpscaleModel({ id: "realesr-animevideov3-x4", name: "AnimeVideo v3" });
  await store.selectUpscaleScale(4);
  expect(fetch).toHaveBeenCalledWith("/api/v1/settings/upscale", expect.any(Object));
  const saved = JSON.parse(localStorage.getItem("manhua_settings"));
  expect(saved.upscaleModel).toBe("realesr-animevideov3-x4");
  expect(saved.upscaleScale).toBe(4);
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/settings.test.js`  
Expected: FAIL (store methods missing)

**Step 3: Implement minimal store changes**

- Add defaults to `settings`:
  - `upscaleModel: "realesrgan-x4plus-anime"`
  - `upscaleScale: 2`
- Add `availableUpscaleModels` list aligned with backend allowlist.
- Add `availableUpscaleScales = [2, 4]`.
- Add methods:
  - `selectUpscaleModel(model)` → save + POST `/api/v1/settings/upscale`.
  - `selectUpscaleScale(scale)` → save + POST `/api/v1/settings/upscale`.
- Keep error handling minimal: log + toast (if store has access) or console.

**Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test -- tests/settings.test.js`  
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/stores/settings.js frontend/tests/settings.test.js
git commit -m "feat: add upscale settings to store"
```

---

### Task 3: Settings UI (minimal controls) + tests

**Files:**
- Modify: `frontend/src/components/SettingsModal.vue`
- Create: `frontend/tests/SettingsModal.test.js`

**Step 1: Write the failing tests**

```javascript
import { describe, it, expect } from "vitest";
import { mount } from "@vue/test-utils";
import SettingsModal from "@/components/SettingsModal.vue";
import { createPinia, setActivePinia } from "pinia";

it("renders upscale controls", () => {
  setActivePinia(createPinia());
  const wrapper = mount(SettingsModal);
  expect(wrapper.find('[data-test=\"upscale-model-select\"]').exists()).toBe(true);
  expect(wrapper.find('[data-test=\"upscale-scale-select\"]').exists()).toBe(true);
});
```

**Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- tests/SettingsModal.test.js`  
Expected: FAIL (controls not present)

**Step 3: Implement UI changes**

- Add a new section under SettingsModal:
  - Upscale model dropdown (bind to `settingsStore.settings.upscaleModel`)
  - Upscale scale dropdown (bind to `settingsStore.settings.upscaleScale`)
- Add `data-test` attributes for tests.
- On change, call `selectUpscaleModel` / `selectUpscaleScale`.

**Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- tests/SettingsModal.test.js`  
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/components/SettingsModal.vue frontend/tests/SettingsModal.test.js
git commit -m "feat: add upscale controls to settings UI"
```

---

### Task 4: Reduce default output size (config-only)

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Update defaults**
- Change `WEBP_QUALITY_FINAL=90` → `80`.
- Ensure `WEBP_SLICES_LOSSLESS=0` is documented as default.

**Step 2: No tests required**

**Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document webp quality defaults"
```

---

## Verification

Run:
```bash
MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q
cd frontend && npm test
```
Expected: PASS

---

## Notes
- This plan intentionally avoids persistent server-side settings.
- If you want persistence later, add a simple `settings.json` store.
