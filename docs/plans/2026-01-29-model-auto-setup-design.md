# Model Auto-Setup (OCR + Inpainting) Design

Date: 2026-01-29  
Project: manhua  
Scope: Startup model availability check and optional auto-download

## 1. Background
Model setup is currently manual. Missing OCR or inpainting models causes silent failures or degraded output. This design adds an automatic, non-blocking startup check to detect and optionally download required models, while keeping the service online even if downloads fail.

## 2. Goals
- Detect OCR and inpainting model availability at startup.
- Optionally download missing models in the background without blocking API startup.
- Expose a status endpoint for UI/ops to inspect readiness.
- Provide clear logs and safe fallback behavior when models are unavailable.

## 3. Non-Goals
- Auto-upgrading model versions without explicit change.
- Automatic model selection or quality tuning.
- Training or fine-tuning models.

## 4. Approach (Recommended: Background Prewarm)
Use a small model registry and a background warmup task in FastAPI lifespan:
1) On startup, spawn a background task to resolve model locations and initialize runtime objects.
2) Update an in-memory `ModelStatus` registry per model.
3) Expose `/api/v1/system/models` for inspection.
4) If a model is missing or fails to initialize, mark it `failed` and allow the pipeline to degrade gracefully.

## 5. Model Registry (Minimal Spec)
Define a small, static registry in code (no new config file needed for MVP):
- `ppocr_det` (HF repo, local cache path)
- `ppocr_rec` (HF repo, local cache path)
- `lama` (local path or HF repo, device via env)

Each entry tracks:
- `name`, `type` (ocr_det / ocr_rec / inpaint)
- `source` (hf repo or local path)
- `local_path`
- `status`: `missing | downloading | ready | failed`
- `error` (optional)

## 6. Data Flow
- **Startup**: FastAPI lifespan schedules `ModelWarmupService.start()`.
- **Warmup**: for each model:
  - check local path / HF cache
  - if missing, download (if enabled)
  - attempt to initialize (OCR loader / LaMa loader)
  - update `ModelStatus`
- **Runtime**: OCR and Inpainting modules consult `ModelStatus` and either run or fallback.

## 7. Configuration (Env)
- `AUTO_SETUP_MODELS=on|off` (default `on`)
- `MODEL_WARMUP_TIMEOUT=300` (seconds, only for startup task)
- `LAMA_DEVICE=cpu|cuda` (default `cpu`)
- Optional overrides:
  - `PPOCR_DET_REPO`, `PPOCR_REC_REPO`
  - `LAMA_MODEL_PATH` or `LAMA_REPO`

## 8. API
`GET /api/v1/system/models`
```json
{
  "ppocr_det": {"status":"ready","path":"..."},
  "ppocr_rec": {"status":"failed","error":"..."},
  "lama": {"status":"ready","device":"cpu"}
}
```

## 9. Error Handling & Safety
- Failures never block server startup.
- Each model is isolated: one failure does not cancel others.
- Logs include actionable hints (missing file, network issue, permission).
- Only allow downloads from known/whitelisted sources to reduce risk.

## 10. Testing
- **Config tests**: `AUTO_SETUP_MODELS=off` skips download; invalid repo is rejected.
- **Warmup tests (mocked)**: simulate success/fail/timeout and assert status updates.
- **Status endpoint**: returns stable schema with `ready/failed` states.
- **Offline mode**: download fails, status shows `failed`, API still starts.

## 11. Rollout
- Phase 1: status endpoint + startup checks (no auto-download).
- Phase 2: background download + initialization.
- Phase 3: UI surface of model readiness + retry trigger (optional).
