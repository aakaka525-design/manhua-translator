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

## Questions / Risks (to validate)
- PaddleOCR concurrency: previous implementation used a global lock to avoid race conditions. Any increase of OCR parallelism must be opt-in and validated under load (crash-free and stable outputs).
- Gemini/PPIO batching: large single prompts can increase tail latency and failure rate; chunking can reduce risk but may change outputs. We will keep chunking controls opt-in and add fallback to preserve quality.
- Chapter translation limits are in-memory (per process). If the deployment uses multiple API workers/containers, limits/deduplication will be per-worker unless moved to a shared store (Redis).
- Signature introspection for `pipeline.process_batch(page_concurrency=...)` is defensive but should be monitored; if signature changes, the feature silently degrades to the pipeline default.
