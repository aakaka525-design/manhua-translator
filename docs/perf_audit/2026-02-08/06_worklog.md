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

### 2026-02-08 (M2 Baseline Sampling)
- Ran 1 real W3-like sample with upscaler disabled to establish a fresh baseline for OCR + Translator.
  - Command (worktree):
    - `QUALITY_REPORT_DIR=output/quality_reports_m2 OCR_RESULT_CACHE_ENABLE=0 UPSCALE_ENABLE=0 python main.py image <img>`
  - Image:
    - `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)
  - Result:
    - Total: 168.3s
    - OCR: 48.0s, regions=84, tile_count=36, tile_avg_ms=1316ms
    - Translator: 101.0s, requests=18 (primary=14, fallback=4)
      - prompt_chars_total=21461, content_chars_total=6017, text_chars_total=1921, ctx_chars_total=2512
    - Inpainter: 18.1s, Renderer: 1.3s, Upscaler: 0s (disabled)

## Open Questions (M2)
- Translator stage time (101s) is much higher than `translator.last_metrics.total_ms` (46.6s) because several fallback paths (per-item retranslate / Google fallback / crosspage extra translation) are not timed today. Next action: add explicit timing + counters for these fallback paths, then decide whether to batch retranslate calls to reduce tail latency and remote call count.

## M3 (Planned / In Progress)

### 2026-02-08 (M3 Kickoff)
- Plan doc added: `docs/perf_audit/2026-02-08/08_m3_plan.md`.
- Current HEAD (start of M3): `fe1c0ff9`.
- Primary blocker to explainability: Translator fallback paths are not timed, causing stage wall-time to exceed `translator.last_metrics.total_ms`.
- Next actions (M3):
  - Add explicit timing + counters for zh retranslate / Google fallback / crosspage extra translation, and include these durations in `TranslatorModule.last_metrics`.
  - Add opt-in batched zh fallback retranslate (`AI_TRANSLATE_ZH_FALLBACK_BATCH=1`) to reduce remote calls and tail latency; default remains off.
  - Run OCR tiling A/B on W3 and record results (defaults unchanged; recommend safe knobs).
  - Re-run W1/W2/W3 end-to-end and update acceptance criteria and roadmap.

### 2026-02-08 (M3 Task 2 - Translator Fallback Timing)
- Added explicit fallback timing + counters to `TranslatorModule.last_metrics`:
  - `zh_retranslate_items` / `zh_retranslate_ms`
  - `google_fallback_items` / `google_fallback_ms`
  - `crosspage_extra_items` / `crosspage_extra_ms`
- `total_ms` now includes these fallback durations (in addition to batch translate timings).
- Added tests to lock behavior: `tests/test_translator_fallback_metrics.py`.

### 2026-02-08 (M3 Task 3 - Batched zh Fallback Retranslate)
- Added opt-in A/B env: `AI_TRANSLATE_ZH_FALLBACK_BATCH=0|1` (default 0).
  - When enabled, zh fallback retranslate uses one `translate_batch()` call (with per-item contexts) instead of per-item `translate()`.
- Added test to lock behavior: `tests/test_translator_fallback_batch.py` (ensures `translate()` is not called in batch mode).
- Next validation: run W1/W2/W3 and spot-check translation quality (batch retranslate can change outputs).

## Questions / Risks (to validate)
- PaddleOCR concurrency: previous implementation used a global lock to avoid race conditions. Any increase of OCR parallelism must be opt-in and validated under load (crash-free and stable outputs).
- Gemini/PPIO batching: large single prompts can increase tail latency and failure rate; chunking can reduce risk but may change outputs. We will keep chunking controls opt-in and add fallback to preserve quality.
- Chapter translation limits are in-memory (per process). If the deployment uses multiple API workers/containers, limits/deduplication will be per-worker unless moved to a shared store (Redis).
- Signature introspection for `pipeline.process_batch(page_concurrency=...)` is defensive but should be monitored; if signature changes, the feature silently degrades to the pipeline default.
