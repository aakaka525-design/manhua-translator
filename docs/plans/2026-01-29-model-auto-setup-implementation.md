# Model Auto-Setup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add startup model availability checks and a status endpoint with optional auto-download/warmup for OCR and inpainting models.

**Architecture:** Introduce a small `core/model_setup.py` registry + warmup service. Hook it into FastAPI lifespan to run in the background and expose status via `/api/v1/system/models`. Failures do not block startup.

**Tech Stack:** Python 3, FastAPI, pytest.

### Task 1: Add model registry + warmup service (TDD)

**Files:**
- Create: `core/model_setup.py`
- Create: `tests/test_model_setup.py`

**Step 1: Write failing tests for registry and warmup**

```python
import pytest

from core.model_setup import ModelRegistry, ModelWarmupService


def test_model_registry_default_state():
    registry = ModelRegistry()
    snapshot = registry.snapshot()
    assert "ppocr_det" in snapshot
    assert snapshot["ppocr_det"]["status"] in {"missing", "ready", "failed"}


@pytest.mark.asyncio
async def test_model_warmup_marks_ready(monkeypatch):
    registry = ModelRegistry()

    async def fake_get_cached_ocr(lang="en"):
        return object()

    def fake_create_inpainter(prefer_lama=True, device="cpu"):
        return object()

    monkeypatch.setattr("core.model_setup.get_cached_ocr", fake_get_cached_ocr)
    monkeypatch.setattr("core.model_setup.create_inpainter", fake_create_inpainter)

    service = ModelWarmupService(registry)
    await service.warmup()

    snapshot = registry.snapshot()
    assert snapshot["ppocr_det"]["status"] == "ready"
    assert snapshot["ppocr_rec"]["status"] == "ready"
    assert snapshot["lama"]["status"] == "ready"
```

**Step 2: Run tests to verify they fail**

Run: `pytest tests/test_model_setup.py::test_model_registry_default_state -v`  
Expected: FAIL (module not found or missing registry)

**Step 3: Implement minimal registry + warmup**

```python
# core/model_setup.py
import os
from dataclasses import dataclass
from typing import Dict, Optional

from core.vision.ocr.cache import get_cached_ocr
from core.vision.inpainter import create_inpainter


@dataclass
class ModelState:
    name: str
    status: str = "missing"  # missing|downloading|ready|failed
    error: Optional[str] = None


class ModelRegistry:
    def __init__(self):
        self._models = {
            "ppocr_det": ModelState(name="ppocr_det"),
            "ppocr_rec": ModelState(name="ppocr_rec"),
            "lama": ModelState(name="lama"),
        }

    def set_status(self, name: str, status: str, error: Optional[str] = None):
        if name in self._models:
            self._models[name].status = status
            self._models[name].error = error

    def snapshot(self) -> Dict[str, Dict[str, Optional[str]]]:
        return {
            name: {"status": m.status, "error": m.error}
            for name, m in self._models.items()
        }


class ModelWarmupService:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    async def warmup(self):
        # OCR det/rec
        try:
            await get_cached_ocr("en")
            await get_cached_ocr("korean")
            self.registry.set_status("ppocr_det", "ready")
            self.registry.set_status("ppocr_rec", "ready")
        except Exception as exc:
            self.registry.set_status("ppocr_det", "failed", str(exc))
            self.registry.set_status("ppocr_rec", "failed", str(exc))

        # LaMa
        try:
            device = os.getenv("LAMA_DEVICE", "cpu")
            create_inpainter(prefer_lama=True, device=device)
            self.registry.set_status("lama", "ready")
        except Exception as exc:
            self.registry.set_status("lama", "failed", str(exc))
```

**Step 4: Run tests to verify they pass**

Run: `pytest tests/test_model_setup.py::test_model_warmup_marks_ready -v`  
Expected: PASS

**Step 5: Commit**

```bash
git add core/model_setup.py tests/test_model_setup.py
git commit -m "feat: add model registry and warmup service"
```

### Task 2: Wire warmup into FastAPI lifespan

**Files:**
- Modify: `app/main.py`

**Step 1: Write failing test for lifespan startup (optional, minimal)**

If skipping test, note in commit message.

**Step 2: Implement background warmup task**

```python
from core.model_setup import ModelRegistry, ModelWarmupService
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    ...
    registry = ModelRegistry()
    app.state.model_registry = registry
    auto_setup = os.getenv("AUTO_SETUP_MODELS", "on").lower() not in {"0","false","off"}
    if auto_setup:
        service = ModelWarmupService(registry)
        app.state.model_warmup_task = asyncio.create_task(service.warmup())
    yield
```

**Step 3: Run tests**

Run: `pytest -q`  
Expected: PASS

**Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: run model warmup in lifespan"
```

### Task 3: Add `/api/v1/system/models` endpoint

**Files:**
- Modify: `app/routes/system.py`
- Create: `tests/test_system_models_endpoint.py`

**Step 1: Write failing test**

```python
from fastapi.testclient import TestClient
from app.main import app


def test_system_models_endpoint():
    client = TestClient(app)
    resp = client.get("/api/v1/system/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "ppocr_det" in data
```

**Step 2: Implement endpoint**

```python
from fastapi import APIRouter, Request

@router.get("/models")
async def get_models_status(request: Request):
    registry = getattr(request.app.state, "model_registry", None)
    if registry is None:
        return {"ppocr_det": {"status": "missing"}, "ppocr_rec": {"status": "missing"}, "lama": {"status": "missing"}}
    return registry.snapshot()
```

**Step 3: Run tests**

Run: `pytest tests/test_system_models_endpoint.py -v`  
Expected: PASS

**Step 4: Commit**

```bash
git add app/routes/system.py tests/test_system_models_endpoint.py
git commit -m "feat: expose model status endpoint"
```

### Task 4: Document env flags

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Update docs**

Add:
```
AUTO_SETUP_MODELS=on
MODEL_WARMUP_TIMEOUT=300
LAMA_DEVICE=cpu
```

**Step 2: Commit**

```bash
git add .env.example README.md
git commit -m "docs: add model auto-setup env flags"
```

### Task 5: Full test run

**Step 1: Run**

`pytest -q`

**Step 2: Report results**

If failures occur, stop and ask for direction.
