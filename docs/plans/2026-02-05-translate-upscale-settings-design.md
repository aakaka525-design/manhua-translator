# Translate + Upscale Runtime Settings (Design)

Date: 2026-02-05

## Summary
Add a minimal settings surface in the frontend to select:
- Translation model
- Upscale model
- Upscale scale (2x / 4x)

Persist settings locally (localStorage) and also push them to the backend as
in-memory overrides. The backend remains compatible with .env defaults and
CLI usage. This keeps changes small and avoids a persistent settings store.

## Goals
- Let users change translation/upscale models and scale from the UI.
- Persist choices locally so refreshes keep the selection.
- Apply changes globally at runtime without editing .env.
- Keep API changes minimal and backward compatible.

## Non-Goals
- No persistent server-side settings store.
- No advanced parameters (tile size, overlap, output format).
- No per-task overrides in API payloads.

## Current State
- Frontend has a translation model selector in settings.js and posts to
  /api/v1/settings/model (in-memory override).
- Upscaler reads env variables (UPSCALE_MODEL, UPSCALE_SCALE, etc.) only.
- /api/v1/settings returns source/target language + ai model.

## Proposed Changes

### Backend API
1) Extend GET /api/v1/settings
- Add fields: upscale_model, upscale_scale.

2) Add POST /api/v1/settings/upscale
- Request body:
  { "model": "realesr-animevideov3-x4", "scale": 4 }
- Behavior:
  - Store in-memory overrides (module-level variables).
  - Validate scale is 2 or 4.
  - Validate model against a small allowlist of supported ncnn models
    (e.g. realesrgan-x4plus-anime, realesrgan-x4plus,
    realesr-animevideov3-x4).

3) Upscaler resolution
- Add helpers that read overrides first, then env, then defaults.
- No changes to .env files at runtime.

### Frontend Settings (Minimal Set)
- Add two controls to the Settings modal:
  - Upscale model (dropdown)
  - Upscale scale (2x / 4x)
- Persist values in localStorage together with existing settings.
- On change:
  - Save local state
  - Call POST /api/v1/settings/upscale
  - If API fails, keep local state and show toast: only local applied

### Data Flow
1) App load:
- settings.js loads localStorage.
- Optionally fetch /api/v1/settings to align defaults if desired.

2) User changes settings:
- Frontend updates localStorage.
- Backend overrides applied in memory.

3) Translation/upscale pipeline:
- Translator uses _model_override (already in place).
- Upscaler uses new override helpers (model + scale).

## Image Size Reduction (Config Recommendation)
To reduce output size without adding new UI:
- Recommend lowering WEBP_QUALITY_FINAL from 90 to 80 in .env.example.
- Keep WEBP_SLICES_LOSSLESS=0 by default.

This does not change runtime unless the user updates their .env.

## Error Handling
- POST /api/v1/settings/upscale returns 422 for invalid scale/model.
- Frontend keeps local values on error and shows a warning toast.

## Testing
Backend:
- test_settings_upscale_update: POST then GET returns new values.
- test_settings_upscale_validation: invalid scale/model -> 422.

Frontend:
- Store test: updates localStorage + triggers API call; handles API failure.

## Rollout
- Deploy backend + frontend together.
- No migration required.
- Existing .env usage still works.

## Risks
- Allowlist drift between frontend and backend.
  - Mitigate by keeping a shared list in frontend and backend, documented.
- Non-persistent overrides could surprise users after restart.
  - Mitigate by clear UI hint: runtime override; restart resets.
