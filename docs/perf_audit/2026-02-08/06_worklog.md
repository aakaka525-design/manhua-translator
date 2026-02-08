# 06 Worklog (OCR/Translator Performance)

Date: 2026-02-08
Branch/worktree: codex/perf-m1-ocr-translator

## Scope
- Only optimize OCR + Translator performance and related scheduling/metrics.
- Do not change upscaler behavior in this round (except fixing blockers if it prevents translation).
- Quality guardrails: changes must not reduce OCR accuracy, translation accuracy, context semantics, or inpaint/repair quality. Defaults must remain safe.

## Progress Log

### 2026-02-08
- Created a dedicated git worktree for performance work: `.worktrees/perf-m1-ocr-translator`.
- Moved uncommitted changes from `main` into this worktree via `git stash apply` to avoid direct edits on `main`.
- Fixed invalid FastAPI 422 status constant in `app/routes/translate.py` (use `status.HTTP_422_UNPROCESSABLE_CONTENT`) to remove deprecation noise.
- Added chapter-level throttling to avoid multi-chapter concurrency blowing up a single container:
  - In-memory inflight registry + lock to dedupe same chapter requests.
  - Global chapter semaphore (env-controlled) to cap concurrent chapter jobs.
  - Pending queue limit (env-controlled) to fail fast when overloaded.
  - Optional page-level concurrency passthrough to `pipeline.process_batch()` (signature introspection).
  - Added tests for 409/429 behaviors and concurrency forwarding.
  - Documented new env vars in `.env.example` and `README.md`.
- Implemented OCR concurrency gate (opt-in) in `core/modules/ocr.py`:
  - Replaced global lock with a bounded semaphore keyed by `OCR_MAX_CONCURRENCY` (default 1).
  - Recorded gate wait time and ensured `last_metrics` are not overwritten later in the method.
- Improved translator observability and batching controls:
  - `core/ai_translator.py`: added `last_metrics` with per-call counters and optional char-budget slicing (`AI_TRANSLATE_BATCH_CHAR_BUDGET`).
  - `core/modules/translator.py`: aggregate `requests_primary/requests_fallback/requests` using translator `last_metrics` (instead of hardcoding).
- Validation: `pytest -q` (347 tests) passes in this worktree.

## M2 (Planned / In Progress)

### 2026-02-08
- Created M2 execution plan: `docs/perf_audit/2026-02-08/07_m2_plan.md`.
- Implemented OCR tiling knobs (env-driven, defaults unchanged):
  - `core/vision/tiling.py`: `OCR_TILE_*` + `OCR_EDGE_*` knobs; rebuild singleton on config signature change.
  - Fixed `TilingManager.overlap_pixels` to use clamped `overlap_ratio` (stability + avoids pathological overlap when tuning).
- Implemented PaddleOCR A/B knobs and extra metrics:
  - `core/vision/ocr/paddle_engine.py`: small-image scaled pass mode (`OCR_SMALL_IMAGE_SCALE_MODE=always|auto|off`) and edge-tile mode (`OCR_EDGE_TILE_MODE=off|on|auto`) + `*_TOUCH_PX`.
  - Recorded edge tile metrics (`last_edge_tile_count`, `last_edge_tile_avg_ms`) in engine and forwarded to `core/modules/ocr.py:last_metrics`.
- Implemented Translator prompt/context observability (env-driven, defaults unchanged):
  - `core/ai_translator.py`: accumulate `prompt_chars_total/content_chars_total/text_chars_total/ctx_chars_total` per attempt (retries included); include in `last_metrics`.
  - `core/modules/translator.py`: optional `AI_TRANSLATE_CONTEXT_CHAR_CAP` (default 0 disabled) and aggregated prompt metrics.
- Added tests:
  - `tests/test_tiling_env_config.py`
  - `tests/test_ai_translator.py` (prompt metrics + retry counting)
  - `tests/test_paddle_engine_perf_flags.py` (small-image scale auto heuristic)
- Validation: `pytest -q` passes (351 tests).
- Next: re-sample baseline with upscaler excluded, then run A/B on:
  - `OCR_TILE_HEIGHT` / `OCR_TILE_OVERLAP_RATIO`
  - `OCR_SMALL_IMAGE_SCALE_MODE=auto`
  - `AI_TRANSLATE_CONTEXT_CHAR_CAP` / `AI_TRANSLATE_BATCH_CHAR_BUDGET`

## Questions / Risks (to validate)
- PaddleOCR concurrency: previous implementation used a global lock to avoid race conditions. Any increase of OCR parallelism must be opt-in and validated under load (crash-free and stable outputs).
- Gemini/PPIO batching: large single prompts can increase tail latency and failure rate; chunking can reduce risk but may change outputs. We will keep chunking controls opt-in and add fallback to preserve quality.
- Chapter translation limits are in-memory (per process). If the deployment uses multiple API workers/containers, limits/deduplication will be per-worker unless moved to a shared store (Redis).
- Signature introspection for `pipeline.process_batch(page_concurrency=...)` is defensive but should be monitored; if signature changes, the feature silently degrades to the pipeline default.
