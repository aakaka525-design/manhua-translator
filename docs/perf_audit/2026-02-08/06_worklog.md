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

### 2026-02-08 (M3 Task 4 - OCR Tiling A/B)
- OCR-only benchmark (W3; `OCR_RESULT_CACHE_ENABLE=0`; model init excluded; single run per config):
  - Image: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)

| OCR_TILE_HEIGHT | OCR_TILE_OVERLAP_RATIO | duration_ms | regions | tile_count | tile_avg_ms |
| --- | --- | --- | --- | --- | --- |
| 1024 | 0.50 | 44793 | 84 | 36 | 1239 |
| 1024 | 0.25 | 31903 | 84 | 25 | 1270 |
| 1536 | 0.25 | 30421 | 86 | 17 | 1780 |

- Conclusion:
  - `1024/0.25` is a clear win with stable regions (84) and fewer tiles; recommended safe knob for long images.
  - `1536/0.25` is slightly faster but changes regions (+2); keep experimental until we confirm no duplicate/noise regression.

### 2026-02-08 (M3 Task 5 - End-to-end Benchmarks)

Common setup (all runs):
- `UPSCALE_ENABLE=0`
- `OCR_RESULT_CACHE_ENABLE=0`
- `QUALITY_REPORT_DIR=output/quality_reports_m3`
- Evidence:
  - Reports: `output/quality_reports_m3/*.json`
  - Translator stage timing: `logs/translator/20260208/translator.log` (raw_regions / translated_done / translator_internal_ms)
  - AI call/fallback evidence: `logs/ai/20260208/ai_translator.log` (timeouts + provider/model fallbacks)

Important note:
- `TranslatorModule` logs raw region count before merge.
- Then it runs `merge_line_regions(...)`, so `regions` in the quality report is the merged region count.

#### W3 (single long page)
- Image: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)
- Raw OCR regions (pre-merge): 84 (stable; see `translator.log`)

| Label | AI_TRANSLATE_ZH_FALLBACK_BATCH | OCR_TILE_OVERLAP_RATIO | total_ms | ocr_ms | translator_stage_ms | translator_internal_ms | gap_pct | raw_regions | merged_regions | translated_done | report |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A1 | 0 | 0.50 | 123264.29 | 44746.41 | 63176.60 | 62272 | 1.43 | 84 | 59 | 42 | `wireless-onahole__chapter-68__9__c708a11e-b8b8-48e4-9cd5-42a049cc1598.json` |
| A2 | 0 | 0.50 | 203465.72 | 44904.60 | 143175.89 | 142349 | 0.58 | 84 | 59 | 42 | `wireless-onahole__chapter-68__9__90240554-72cb-4070-a502-d7627247c778.json` |
| B1 | 1 | 0.25 | 134515.78 | 31405.14 | 88764.54 | 87936 | 0.93 | 84 | 58 | 42 | `wireless-onahole__chapter-68__9__e0aed731-7874-479c-8184-901903555a7a.json` |
| B2 | 1 | 0.25 | 119098.35 | 31089.75 | 73614.15 | 72787 | 1.12 | 84 | 58 | 42 | `wireless-onahole__chapter-68__9__4e2e3452-7389-4c97-8068-171a1d132009.json` |
| C1 (safe) | 0 | 0.25 | 133075.09 | 31343.50 | 87481.19 | 86655 | 0.94 | 84 | 58 | 42 | `wireless-onahole__chapter-68__9__6a090d5f-bb18-41a0-ad9f-9402cb301b16.json` |

Observations:
- Explainability: translator stage vs internal translate time gap stays <= 1.43% (PASS).
- OCR: overlap ratio 0.25 improves OCR stage (~44.8s -> ~31.1s) without reducing raw region count (84).
- Translator tail: A2 shows large long-tail even under same knob set. This aligns with remote timeouts and fallback stacking, not local CPU saturation.
  - Evidence (from `logs/ai/20260208/ai_translator.log`):
    - `fallback provider=ppio ... due to primary error=primary timeout after 12000ms`
    - `fallback provider=gemini model=gemini-2.5-flash due to primary error=primary timeout after 12000ms`

Quality quick-check (heuristic, merged regions on W3):
- For multiple W3 runs, `no_cjk_with_ascii=4` (English-only outputs) and remained stable (no regression observed).
- Manual semantic spot-check (10 samples) still required before promoting any default changes.

#### W1 (single short page)
- Image: `/Users/xa/Desktop/projiect/manhua/data/raw/sexy-woman/chapter-1/15.jpg`
- Timings (report): total=86342.96ms, ocr=17226.63ms, translator=59582.24ms
- Report: `sexy-woman__chapter-1__15__39249e5d-dc7a-4172-9838-86af55c554eb.json`

#### W2 (chapter, `-w 2`)
- Input: `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/` (9 pages)
- Note: per-page totals overlap due to concurrency; use this table to locate slow pages (tail).

| Page | total_ms | ocr_ms | translator_stage_ms | report |
|---:|---:|---:|---:|---|
| 1 | 98381.19 | 19762.15 | 69688.25 | `wireless-onahole__chapter-68__1__50ccdef4-c4a8-4234-a4ba-4dedbb187d98.json` |
| 2 | 72392.01 | 32648.64 | 30995.72 | `wireless-onahole__chapter-68__2__783a63dd-5577-4f42-af32-105c1c315120.json` |
| 3 | 65619.24 | 14948.36 | 39676.08 | `wireless-onahole__chapter-68__3__4543ceb9-2659-47e7-864b-75c88df2dfe8.json` |
| 4 | 65621.96 | 14077.92 | 42281.58 | `wireless-onahole__chapter-68__4__9854e685-d909-4554-b940-0d85cd5f7f8c.json` |
| 5 | 59390.36 | 15572.56 | 31749.88 | `wireless-onahole__chapter-68__5__7ba7e746-7417-49dc-aa33-86dff2ec0b0f.json` |
| 6 | 66476.74 | 14208.14 | 42382.42 | `wireless-onahole__chapter-68__6__b7c94e49-a7de-4154-9130-e0af5425563b.json` |
| 7 | 132200.69 | 18136.94 | 99890.27 | `wireless-onahole__chapter-68__7__d075436d-85cb-46b4-8cf7-c8379ad65fc7.json` |
| 8 | 54765.80 | 12157.19 | 33614.00 | `wireless-onahole__chapter-68__8__c9b0dfb9-7ac7-42cf-a744-32ad5d208040.json` |
| 9 | 133075.09 | 31343.50 | 87481.19 | `wireless-onahole__chapter-68__9__6a090d5f-bb18-41a0-ad9f-9402cb301b16.json` |

Slow pages to investigate first:
- Page 7/9 dominate tail by total_ms; translator stage is the major contributor on both.

## Questions / Risks (to validate)
- PaddleOCR concurrency: previous implementation used a global lock to avoid race conditions. Any increase of OCR parallelism must be opt-in and validated under load (crash-free and stable outputs).
- Gemini/PPIO batching: large single prompts can increase tail latency and failure rate; chunking can reduce risk but may change outputs. We will keep chunking controls opt-in and add fallback to preserve quality.
- Chapter translation limits are in-memory (per process). If the deployment uses multiple API workers/containers, limits/deduplication will be per-worker unless moved to a shared store (Redis).
- Signature introspection for `pipeline.process_batch(page_concurrency=...)` is defensive but should be monitored; if signature changes, the feature silently degrades to the pipeline default.
- Missing attribution in reports: quality reports currently do not persist the env knob snapshot (e.g. overlap ratio / batch fallback), making A/B attribution rely on external notes. Consider writing a minimal `run_config` field into quality report JSON.

## Follow-ups (M3.1)
### Translator: missing-number recovery (reduce per-item fallback + tail + fail markers)
Evidence:
- AI logs can contain repeated warnings like `AI response missing number N`, indicating truncated/format-drift numbered outputs.
- Under high concurrency, this can cascade into `[翻译失败]` regions if the batch cannot be recovered and all fallbacks are exhausted.

Implementation (branch `codex/stress-quality-fixes`):
- `core/ai_translator.py:AITranslator.translate_batch()`:
  - Immediate strict-output retry when numbered items are missing (`max_retries=2`).
  - Adds a token headroom bonus via `AI_TRANSLATE_BATCH_MAX_TOKENS_MISSING_NUMBER_BONUS` (default 800) on strict retries.
  - If missing-number persists after retries, treat it as fallback-worthy so the fallback chain (gemini model fallback / provider fallback) can recover instead of returning all failure markers.
  - If a full batch still returns all failures, chunk fallback now shrinks `fallback_chunk_size` for small batches so it actually reduces prompt/output size (previously `min(12, chunk_size)` could be >= batch size and no fallback happened).
- Tests:
  - `tests/test_ai_translator.py::test_translate_batch_retries_when_numbered_output_missing_items`
  - `tests/test_ai_translator.py::test_translate_batch_falls_back_when_missing_numbered_items_persist`
  - `tests/test_ai_translator.py::test_translate_batch_chunk_fallback_shrinks_when_default_chunk_is_too_large`

Status / next evidence:
- Needs cloud stress re-run evidence (S6/S9, UPSCALE=0) to confirm `pages_has_failure_marker` drops (target 0) without introducing mixed-language regressions.

Open question:
- Consider similar recovery for `output_format=json` when JSON extraction yields fewer than expected objects (crosspage path). Only do if stress evidence shows json parse is a contributor.

### W3 A/B: `AI_TRANSLATE_PRIMARY_TIMEOUT_MS` 12000 vs 15000 (Gemini)
Context:
- Workload: W3 `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- Purpose: validate whether 12s is too tight for `gemini-3-flash-preview` and causes avoidable timeout -> fallback stacking.

Evidence (pipeline metrics + AI log counters):

| Label | AI_TRANSLATE_PRIMARY_TIMEOUT_MS | total_ms | ocr_ms | translator_ms | requests_primary | requests_fallback | zh_retranslate_items | zh_retranslate_ms | ai_timeouts | ai_fallback_provider | missing_retry | no_cjk_with_ascii | reports |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| T12 | 12000 | 169307 | 31931 | 120126 | 7 | 9 | 4 | 43779.62 | 6 | 6 | 7 | 9 | `/tmp/quality_reports_m3_20260208_153742/wireless-onahole__chapter-68__9__1ca08ace-9c27-407a-ab6a-b4bf3da9b09c.json` |
| T15 | 15000 | 132304 | 31960 | 83841 | 8 | 5 | 1 | 4032.74 | 2 | 2 | 6 | 4 | `/tmp/quality_reports_m3_20260208_154433_t15/wireless-onahole__chapter-68__9__fdeab5ef-320b-47ed-ad3c-f542ab076c5f.json` |

Notes:
- `ai_timeouts` / `ai_fallback_provider` / `missing_retry` are counted from `MANHUA_LOG_DIR/ai/20260208/ai_translator.log`.
  - T12: `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.O1X8MByczB`
  - T15: `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.U375CSsvgC`
- OCR quality guard: both runs `regions_detected=84` (PASS) and merged region count stable (58 in quality report).
- Failure marker guard: both runs `"[翻译失败]"=0` in quality report (PASS).
- Mixed-language heuristic: `no_cjk_with_ascii` drops from 9 -> 4 when timeout is raised (quality improvement).

Root cause hypothesis (supported by prior stats + this A/B):
- `gemini-3-flash-preview` batch latencies often sit near 10-12s p95/p99; with a 12s guard, small overhead (event loop scheduling, retry backoff, provider variability) frequently crosses the threshold and triggers `asyncio.wait_for` timeout.
- Each timeout causes a fallback call (gemini-2.5-flash or provider fallback), and those fallbacks can be slower, compounding tail latency and increasing remote calls.

Recommendation (config-only; keep code default unchanged):
- For deployments using Gemini with fallback chain enabled, set `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` in docker env/.env to reduce avoidable timeout->fallback stacking and improve p95/p99 stability.

Open questions:
- W2 stability under concurrency: CLOSED (W2 full chapter re-run at `-w 2`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`; see "W2 full chapter sampling" section below).
- 18000ms: NOT PLANNED (keep `15000ms` as the deploy-side recommendation unless new evidence shows persistent timeout stacking).

### W2 tail sampling (7+9, `-w 2`): `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
Context:
- Workload: W2 tail pages (chapter-68): `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/7.jpg` + `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg`
- Concurrency: `main.py chapter ... -w 2` (2 pages in-flight)
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- Output dir: `/tmp/perf_m3_ch68_tail_t15`
- Reports: `/tmp/quality_reports_m3_w2tail_t15_20260208_161650/*.json`
- Logs:
  - `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.OfkmC0GfFL`
  - AI log: `/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.OfkmC0GfFL/ai/20260208/ai_translator.log`
  - Translator log: `/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.OfkmC0GfFL/translator/20260208/translator.log`
- Purpose: verify that the `15000ms` recommendation remains stable under chapter concurrency tail pages.

Evidence:
- AI log counters (global for this run):
  - `primary timeout after 15000ms`: 3
  - `fallback provider=`: 3
  - `missing number|missing items` lines: 29

Per-page (quality report; note: regions in report are merged, raw OCR regions are shown in translator.log):

| page | total_ms | ocr_ms | translator_ms | regions_report | `[翻译失败]` | no_cjk_with_ascii | ai_timeouts | ai_fallback_provider | missing_number_lines | report_path |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 7 | 99522.65 | 20162.19 | 64505.19 | 33 | 0 | 2 | 3 | 3 | 29 | `/tmp/quality_reports_m3_w2tail_t15_20260208_161650/tmp__ch68-tail_852n0l__7__250ba346-b3a5-48ff-8e4e-a3eab01fec7f.json` |
| 9 | 173092.51 | 52294.92 | 104037.59 | 58 | 0 | 0 | 3 | 3 | 29 | `/tmp/quality_reports_m3_w2tail_t15_20260208_161650/tmp__ch68-tail_852n0l__9__4b4dbc82-6830-402a-ba35-819d642083ef.json` |

Notes:
- Translator log shows raw OCR region counts:
  - Page 7 task `250ba346-...`: "开始翻译 38 个区域"
  - Page 9 task `4b4dbc82-...`: "开始翻译 84 个区域"
- Quality guardrails:
  - `[翻译失败]` stays 0 on both pages (PASS)
  - `hangul_left=0` on both pages (PASS)
  - `no_cjk_with_ascii` is low (page 9 is 0; page 7 has 2 entries, likely short tags/labels)

Interpretation:
- Under `-w 2` concurrency, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` still has a small number of timeouts (3), but no failure markers or Hangul leftovers.
- This supports keeping `15000ms` as a deploy-side recommendation for Gemini + fallback chain, while acknowledging chapter-level p95 is still dominated by remote-call tail latency and other translator strategies (M1#3/#4) are needed to further reduce long-tail.

Open questions / follow-ups:
- W2 full chapter (9 pages) under `-w 2` + `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`: CLOSED (re-run completed; see next section).

Repro / extraction commands:
- Count timeouts/fallbacks:
  - `rg -n "primary timeout after" "$MANHUA_LOG_DIR/ai/20260208/ai_translator.log" | wc -l`
  - `rg -n "fallback provider=" "$MANHUA_LOG_DIR/ai/20260208/ai_translator.log" | wc -l`
- Parse W2 tail quality reports (timings + guardrails):
  ```bash
  python - <<'PY'
  import json, glob
  paths = sorted(glob.glob("/tmp/quality_reports_m3_w2tail_t15_20260208_161650/*.json"))
  for p in paths:
      with open(p, "r", encoding="utf-8") as f:
          d = json.load(f)
      t = d.get("timings_ms") or {}
      regions = d.get("regions") or []
      fail = sum(1 for r in regions if (r.get("target_text") or "").startswith("[翻译失败]"))
      print(
          p,
          {"total": t.get("total"), "ocr": t.get("ocr"), "translator": t.get("translator")},
          "regions",
          len(regions),
          "fail",
          fail,
      )
  PY
  ```

### W2 full chapter sampling (9 pages, `-w 2`): `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
Context:
- Workload: W2 full chapter-68 (9 pages): `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/*`
- Concurrency: `main.py chapter ... -w 2`
- Fixed knobs: `UPSCALE_ENABLE=0`, `OCR_RESULT_CACHE_ENABLE=0`, `OCR_TILE_OVERLAP_RATIO=0.25`, `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- Output dir: `/tmp/perf_m3_ch68_full_t15` (note: output dir existed and might be overwritten)
- Reports: `output/quality_reports_m3_w2full_t15/*.json`
- Logs:
  - `MANHUA_LOG_DIR=/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.yIOpbiWXDs`
  - AI log: `/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.yIOpbiWXDs/ai/20260208/ai_translator.log`
  - Translator log: `/var/folders/7x/xmj28_bn6w7_8pcmtl3vqdc40000gn/T/tmp.yIOpbiWXDs/translator/20260208/translator.log`
- Purpose: close the "W2 full chapter sampling" gap for promoting the `15000ms` deploy-side recommendation.

Evidence:
- CLI summary (hot run):
  - success=9, fail=0
  - total regions (merged)=259
  - total wall-time=484.3s (53.8s/page)
- AI log counters (global for this run):
  - `primary timeout after 15000ms`: 7
  - `fallback provider=`: 14
  - `missing number|missing items` lines: 65
- Report schema upgrades (commit `44449b9`):
  - Each quality report now includes `run_config` (sanitized env whitelist), `process` (`cpu_user_s`, `cpu_system_s`, `max_rss_mb`), and `queue_wait_ms`.

Per-page (quality report; merged regions):

| page | total_ms | ocr_ms | translator_ms | regions_report | fail_regions | empty_target | hangul_left | no_cjk_with_ascii | report |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 102033.27 | 33840.82 | 57349.82 | 28 | 0 | 4 | 0 | 3 | `wireless-onahole__chapter-68__1__dec898bf-fd8f-47e9-b78e-b3f8cd2f91dc.json` |
| 2 | 70669.95 | 32749.19 | 28576.96 | 21 | 0 | 6 | 0 | 1 | `wireless-onahole__chapter-68__2__7218b24c-c684-4c27-a197-8ebfacc7cebc.json` |
| 3 | 67870.85 | 15398.64 | 40335.49 | 29 | 0 | 4 | 0 | 2 | `wireless-onahole__chapter-68__3__4d50b635-6b28-478a-ae0c-fa50a7efe295.json` |
| 4 | 70503.34 | 14732.51 | 45424.79 | 28 | 0 | 2 | 0 | 4 | `wireless-onahole__chapter-68__4__95c2fca5-6c8b-42ee-ada2-53b630594b1b.json` |
| 5 | 58872.88 | 15660.94 | 25571.56 | 23 | 0 | 1 | 0 | 2 | `wireless-onahole__chapter-68__5__35979747-ef56-498a-907d-1a1c98ba3d27.json` |
| 6 | 63112.68 | 14758.95 | 36438.65 | 23 | 0 | 2 | 0 | 2 | `wireless-onahole__chapter-68__6__1bbfe6be-7ff3-48ac-b86d-55958c06aa21.json` |
| 7 | 75679.38 | 18614.87 | 40828.15 | 33 | 0 | 1 | 0 | 4 | `wireless-onahole__chapter-68__7__36d20521-d9aa-4505-8eee-5954494e1c58.json` |
| 8 | 77561.20 | 12500.65 | 31941.60 | 16 | 0 | 0 | 0 | 0 | `wireless-onahole__chapter-68__8__0f37c83c-af29-4e1a-8937-d354a5bd86d9.json` |
| 9 | 188303.02 | 32993.90 | 133648.88 | 58 | 0 | 12 | 0 | 4 | `wireless-onahole__chapter-68__9__72a59579-86bd-4b3a-bc86-83e415c7bfe6.json` |

Aggregated timings (nearest-rank p50/p95; N=9 so p95==max):
- total: p50=70.7s, p95=188.3s (page 9)
- ocr: p50=15.7s, p95=33.8s
- translator: p50=40.3s, p95=133.6s (page 9)
- process peak (from reports): `max_rss_mb` ~= 5263.7

Quality guardrails:
- `[翻译失败]` regions: 0 (PASS)
- `hangul_left` regions: 0 (PASS)
- `no_cjk_with_ascii` exists (<=4/page), likely short tags/labels; not a systemic mixed-language regression.

Interpretation:
- Under chapter concurrency `-w 2`, `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000` remains stable (no failure markers, no Hangul leakage).
- The long-tail is still dominated by remote-call latency and fallback/retry (timeouts=7, fallback provider=14, missing-number lines=65). Next evidence target is higher-concurrency cloud stress + crash-mode inspection (OOMKilled vs exception).

Repro / extraction commands:
- Count timeouts/fallbacks:
  - `rg -n "primary timeout after" "$MANHUA_LOG_DIR/ai/20260208/ai_translator.log" | wc -l`
  - `rg -n "fallback provider=" "$MANHUA_LOG_DIR/ai/20260208/ai_translator.log" | wc -l`
  - `rg -n "missing (number|items)" "$MANHUA_LOG_DIR/ai/20260208/ai_translator.log" | wc -l`
- Parse W2 full quality reports (timings + guardrails):
  ```bash
  python - <<'PY'
  import json, glob, re

  CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af]")
  HANGUL = re.compile(r"[\uac00-\ud7af]")
  ASCII = re.compile(r"[A-Za-z]")

  def no_cjk_with_ascii(s: str) -> bool:
      return bool(s) and (not CJK.search(s)) and bool(ASCII.search(s))

  paths = sorted(glob.glob("output/quality_reports_m3_w2full_t15/*.json"))
  for p in paths:
      with open(p, "r", encoding="utf-8") as f:
          d = json.load(f)
      t = d.get("timings_ms") or {}
      regs = d.get("regions") or []
      fail = sum(1 for r in regs if "[翻译失败]" in (r.get("target_text") or ""))
      empty = sum(1 for r in regs if (r.get("target_text") or "") == "")
      hangul = sum(1 for r in regs if HANGUL.search(r.get("target_text") or ""))
      no_cjk = sum(1 for r in regs if no_cjk_with_ascii(r.get("target_text") or ""))
      print(
          p,
          {"total": t.get("total"), "ocr": t.get("ocr"), "translator": t.get("translator")},
          "regions",
          len(regs),
          "fail",
          fail,
          "empty",
          empty,
          "hangul",
          hangul,
          "no_cjk_with_ascii",
          no_cjk,
      )
  PY
  ```

## 2026-02-08 Stability: multi-chapter crash mitigation (task store + SSE backpressure)

Problem statement:
- On Docker deployments, running multiple chapter translations can crash the API process (likely memory pressure / OOM). This is amplified when:
  - Chapter jobs run concurrently (chapter_slots/page_concurrency)
  - Each finished page keeps full `TaskContext.regions` in memory
  - SSE clients are slow/disconnected and progress events pile up

Root-cause evidence (code-level):
- `app/routes/translate.py` keeps `_tasks: Dict[UUID, TaskContext]` forever; chapter processing stores *all* page contexts up front and those contexts are later populated with full `regions` payload.
- `broadcast_event()` previously used `await queue.put(...)` on per-client `asyncio.Queue()` with no `maxsize`. If a client is slow, this can either:
  - grow memory unbounded (unbounded queue), or
  - apply backpressure and block progress callbacks if queue is bounded later.

Mitigation implemented (branch `codex/stability-multi-chapter`):
- Bounded task store:
  - `_tasks` switched to `OrderedDict` with pruning on insert (LRU-style).
  - On store, task is stripped (`regions=[]`, `crosspage_debug=None`) to avoid retaining large payloads.
  - Knobs (deploy-side):
    - `TRANSLATE_TASK_MAX_STORED` (default 2000)
    - `TRANSLATE_TASK_TTL_SECONDS` (default 21600)
    - `TRANSLATE_TASK_STRIP_REGIONS` (default 1)
- SSE backpressure safety:
  - Listener queues are created with `SSE_QUEUE_MAXSIZE` (default 200).
  - `broadcast_event()` uses `put_nowait()` and drops the oldest event on `QueueFull` to keep latest.
  - Iterates over `list(_listeners)` to avoid "set changed size during iteration" hazards.

Quality impact:
- No change to OCR/Translator logic or outputs.
- `/translate/task/{task_id}` still serves status/output path; it never exposed regions, so stripping is safe.
- SSE progress streams may skip intermediate events for slow clients, but should continue to deliver newest progress and completion.

Verification:
- Added tests:
  - `tests/test_translate_task_store_limits.py` (eviction + strip)
  - `tests/test_translate_sse_backpressure.py` (no deadlock on full queue; keep latest event)
- Full suite: `pytest -q` PASS.

Open question:
- Crash mode inspection (OOMKilled vs unhandled exception): CLOSED (cloud S3b/S6/S9 all show `OOMKilled=false`, `RestartCount=0`, kernel OOM lines=0; see sections below).

## 2026-02-08 Cloud Stress S2: Hangul leakage fix validated (UPSCALE=0)

Context:
- Server: Docker compose (API container `manhua-translator-api-1`)
- Branch: `codex/stress-quality-fixes`
- Deployed commit: `27e8b96`
- Stress workload: 3 concurrent chapters (total 42 pages), each runs `python main.py chapter ... -w 2`
- Env (key):
  - `UPSCALE_ENABLE=0`
  - `OCR_RESULT_CACHE_ENABLE=0`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`

Evidence (quality report lists on server):
- Before fix: `output/quality_reports/_stress_20260208_134907.list`
- After fix: `output/quality_reports/_stress_20260208_142518_s2_afterfix.list`

Aggregated results (parsed inside container with a python snippet; nearest-rank p50/p95):
- Before fix (`_stress_20260208_134907.list`):
  - `pages_total=42`, `[翻译失败]=0`
  - `pages_has_hangul=2`, `regions_with_hangul=2`
  - timings (ms): `translator_p95=66908.39`, `translator_max=85901.53`, `total_p95=74367.29`
  - Hangul files:
    - `hole-inspection-is-a-task__chapter-1__1__42eef2ef-175a-4488-b03c-12f91f5e85d2.json`
    - `taming-a-female-bully__chapter-57-raw__19__3a14ca9e-2e7b-40db-863a-776cac923019.json`
- After fix (`_stress_20260208_142518_s2_afterfix.list`):
  - `pages_total=42`, `[翻译失败]=0`
  - `pages_has_hangul=0`, `regions_with_hangul=0`
  - timings (ms): `translator_p95=29367.05`, `translator_max=77958.95`, `total_p95=66470.57`

Root cause (quality regression source, now fixed):
1) zh fallback input selection:
   - Previous behavior: when initial translation differed from `src_text`, fallback used `fallback_input=translation` even if translation contained Hangul.
   - Symptom: a corrupted model output like `"<hangul> (After completing the"` would get retranslated from itself and stay corrupted, leaving Hangul in zh output.
   - Fix: if `translation` contains Hangul, force `fallback_input=src_text` (never feed corrupted output back).
2) SFX path for unknown Hangul:
   - Previous behavior: `translate_sfx()` returns original Hangul when not in dictionary; pipeline rendered Hangul as new overlay text.
   - Fix: for zh targets, if `translate_sfx()` output still contains Hangul, set `target_text=\"\"` to keep original art/text (no inpaint + no render).

TDD coverage:
- Added regression tests: `tests/test_translator_hangul_guard.py`
- Updated expectation: `tests/test_translator_sfx.py` unknown Hangul SFX keeps original art (`target_text==\"\"`) for zh targets.

Open questions / follow-ups:
- Docker CPU image has no LaMa inpainting, uses OpenCV fallback (seen in chapter logs). This may affect erase quality and latency; decide if we need LaMa on server deployments.
- Crash reproduction: not observed at 3 concurrent chapters with `UPSCALE_ENABLE=0`. If user still sees crashes, likely higher concurrency (more simultaneous chapters) and/or upscaler enabled.

## 2026-02-08 Cloud Stress S3b: API multi-chapter (4 chapters, 43 pages, UPSCALE=0) on 185.218.204.62
Context:
- Server: `185.218.204.62` (docker)
- Repo: `/root/manhua-translator`
- Deployed branch: `codex/stress-quality-fixes` (includes commit `4e6263a`)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_190604_api_s3b`
- Report list: `output/quality_reports/_stress_20260208_190604_api_s3b.list` (43 json)
- Trigger: start 4 chapters concurrently via API `POST /api/v1/translate/chapter`
- Env (key; no secrets):
  - `UPSCALE_ENABLE=0`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
  - `AI_TRANSLATE_BATCH_CONCURRENCY=2`
  - `AI_TRANSLATE_FASTFAIL=1`

Evidence:
- Aggregated report summary (python snippet on server; nearest-rank p50/p95):
  - `pages_total=43`
  - quality:
    - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
    - `pages_has_failure_marker=1`, `regions_with_failure_marker=7` (FAIL)
    - `no_cjk_with_ascii=23`, `empty_target_regions=52`
  - timings (ms):
    - `translator_p50=14277`, `translator_p95=53667`, `translator_max=97212`
    - `total_p95=72163`, `total_max=121280`
  - process peak (from reports):
    - `max_rss_max_mb=4376.7`
  - failure file:
    - `taming-a-female-bully__chapter-57-raw__12__8d767d9a-dbcb-410a-a621-58f9512b8f9f.json` (7 regions, all `[翻译失败]`)
- Failure page details (from report):
  - image: `data/raw/taming-a-female-bully/chapter-57-raw/12.jpg`
  - timings (ms): `translator=97212`, `total=108542`
  - regions_total=7, fail_regions=7
- Docker/kernel evidence (server):
  - container: `manhua-translator-api-1` is healthy
  - `OOMKilled=false`, `RestartCount=0`
  - kernel OOM lines: `0` (`/tmp/kernel_oom_s3b_20260208_190604.txt`)

Interpretation:
- Hangul leakage regression stays fixed under API multi-chapter concurrency (good).
- Under this load, Gemini overload / timeout still happens (AI log shows many `503 UNAVAILABLE` and timeouts), and at least one page fell through all fallbacks -> `[翻译失败]` (quality regression).
- Memory peak is already ~4.3GB at 4 concurrent chapters; higher concurrency is likely to increase OOM risk.

Open questions / follow-ups:
- Concurrency escalation: run 6 and 9 concurrent chapters (still `UPSCALE_ENABLE=0`) to find crash boundary and measure `[翻译失败]` rate under load.
- Mitigation candidates (low risk, quality-preserving):
  - Add a global AI-call semaphore (cross-task) to keep provider 503/timeout rate low.
  - Cap chapter concurrency (`TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS`) to avoid pushing provider into overload.

## 2026-02-08 Cloud Stress S6: API multi-chapter (6 chapters, 108 pages, UPSCALE=0) on 185.218.204.62
Context:
- Server: `185.218.204.62`
- Trigger: API `POST /api/v1/translate/chapter` (6 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_192710_api_s6`
- Report list: `output/quality_reports/_stress_20260208_192710_api_s6.list` (108 json; expected_pages=108)
- Env (key; no secrets):
  - `UPSCALE_ENABLE=0`
  - `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
  - `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=2`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`

Evidence:
- Aggregated report summary (nearest-rank p50/p95):
  - `pages_total=108`
  - quality:
    - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
    - `pages_has_failure_marker=4`, `regions_with_failure_marker=18` (FAIL)
    - `no_cjk_with_ascii=50`, `empty_target_regions=209`
  - timings (ms):
    - `translator_p50=11313`, `translator_p95=38087`, `translator_max=54892`
    - `total_p95=66145`, `total_max=82515`
  - process peak (from reports):
    - `max_rss_max_mb=5666.1`
  - failure files (examples):
    - `hole-inspection-is-a-task__chapter-15-raw__4__8be15ec2-5a36-4d69-8ba8-bfd6a1055b08.json` (6 regions, all `[翻译失败]`)
    - `hole-inspection-is-a-task__chapter-12-raw__5__35d4e1e2-9734-4959-bc8f-5741d062159c.json` (8 regions, 3 failed)
- Docker/kernel:
  - api container healthy; `OOMKilled=false`, `RestartCount=0`
  - kernel OOM lines: `0` (`/tmp/kernel_oom_s6_20260208_192710.txt`)

Interpretation:
- With 6 concurrent chapters (page inflight up to ~12), the system stays up, but translation failure markers increase (4/108 pages).
- RSS peak rises to ~5.7GB. This supports the hypothesis that higher concurrency can push both:
  - provider overload (timeouts/503 -> failures), and
  - memory pressure (risk of OOM at higher concurrency).

Open questions / follow-ups:
- Run 9 concurrent chapters (short-window sampling is ok) to confirm whether OOM/restart appears and how fast `[翻译失败]` rate grows.
- If S9 further degrades: implement global backpressure (max in-flight pages and/or AI-call semaphore) and rerun S6/S9 for evidence.

## 2026-02-08 Cloud Stress S9: API multi-chapter (9 chapters, 211 pages, UPSCALE=0) on 185.218.204.62
Context:
- Server: `185.218.204.62`
- Trigger: API `POST /api/v1/translate/chapter` (9 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260208_193832_api_s9`
- Report list: `output/quality_reports/_stress_20260208_193832_api_s9.list` (211 json; expected_pages=211)
- Env (key; no secrets):
  - `UPSCALE_ENABLE=0`
  - `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=9`
  - `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=2`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`

Evidence:
- Aggregated report summary (nearest-rank p50/p95):
  - `pages_total=211`
  - quality:
    - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
    - `pages_has_failure_marker=6`, `regions_with_failure_marker=16` (FAIL)
    - `no_cjk_with_ascii=78`, `empty_target_regions=340`
  - timings (ms):
    - `translator_p50=11839`, `translator_p95=42156`, `translator_max=73991`
    - `total_p95=72736`, `total_max=110472`
  - process peak (from reports):
    - `max_rss_p95_mb=5667.7`, `max_rss_max_mb=5749.6`
  - failure files (examples):
    - `taming-a-female-bully__chapter-57-raw__12__f2284788-3bda-4e6e-80b9-276dcdb1c5cc.json`
    - `hole-inspection-is-a-task__chapter-12-raw__7__35a2925b-cdf1-4124-bc54-b1e6177c44eb.json`
- Docker/kernel:
  - api container healthy; `OOMKilled=false`, `RestartCount=0`
  - kernel OOM lines: `0` (`/tmp/kernel_oom_s9_20260208_193832.txt`)

Interpretation:
- With `UPSCALE_ENABLE=0`, the API container did not crash up to 9 concurrent chapters (no OOM/restarts observed).
- Quality still degrades with concurrency: failure markers persist and increase vs S3b, which aligns with provider overload / fallback exhaustion rather than local compute.

Open questions / follow-ups:
- Crash reproduction (UPSCALE=0): CLOSED (not reproduced up to 9 concurrent chapters in S9).
- Next: implement global backpressure to reduce provider overload, then re-run S6/S9 to target `"[翻译失败]"=0` while keeping `pages_has_hangul=0`.

## 2026-02-09 Cloud Stress S6 Re-run: missing-number recovery + global AI-call backpressure (6 chapters, 104 pages, UPSCALE=0) on 185.218.204.62

Purpose:
- Validate whether translator failure markers (`[翻译失败]`) can be driven back to 0 under multi-chapter API load without reintroducing Hangul leakage.
- Close the follow-up from S6/S9: add global backpressure and re-run for evidence.

Context:
- Server: `185.218.204.62` (docker)
- Repo: `/root/manhua-translator`
- Deployed branch: `codex/stress-quality-fixes`
- Deployed commit: `3bd11f8` (merge commit; includes missing-number recovery + `AI_TRANSLATE_MAX_INFLIGHT_CALLS` backpressure)
- Trigger: start 6 chapters concurrently via API `POST /api/v1/translate/chapter`
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260209_064151_api_s6_missingfix`
- Evidence (server artifacts):
  - report list: `output/quality_reports/_stress_20260209_064151_api_s6_missingfix.list` (104 json; expected_pages=104)
  - summary: `output/quality_reports/_stress_20260209_064151_api_s6_missingfix.summary.json`
  - failures: `output/quality_reports/_stress_20260209_064151_api_s6_missingfix.failures.txt`
  - docker: `output/quality_reports/_stress_20260209_064151_api_s6_missingfix.docker_state.txt`
  - kernel OOM: `/tmp/kernel_oom_20260209_064151_api_s6_missingfix.txt` (0 lines)

Dataset (chapters started concurrently; expected_pages=104):
- `hole-inspection-is-a-task/chapter-16-raw` (32)
- `hole-inspection-is-a-task/chapter-18-raw` (29)
- `taming-a-female-bully/chapter-57-raw` (23)
- `hole-inspection-is-a-task/chapter-12-raw` (13)
- `hole-inspection-is-a-task/chapter-1` (6)
- `wireless-onahole/chapter-71-raw` (1)

Env (key; no secrets):
- `UPSCALE_ENABLE=0`
- `OCR_TILE_OVERLAP_RATIO=0.25`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`
- `AI_TRANSLATE_FASTFAIL=1`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=4`
- `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
- `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=2`

Evidence (summary):
- `pages_total=104`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `pages_has_failure_marker=2`, `regions_with_failure_marker=3` (NOT PASS; target is 0)
  - `no_cjk_with_ascii=43`, `empty_target_regions=193`
- timings (ms; nearest-rank p50/p95):
  - `translator_p50=21014`, `translator_p95=102972`, `translator_max=199678`
  - `ocr_p50=1777`, `ocr_p95=33364`, `ocr_max=39303`
  - `total_p50=35477`, `total_p95=107546`, `total_max=215703`
- process peak (from reports):
  - `max_rss_p95_mb=3985.7`, `max_rss_max_mb=3985.7`
- failure pages (from summary + failures.txt):
  - `data/raw/hole-inspection-is-a-task/chapter-12-raw/5.jpg`: `regions=8`, `fail_regions=2`, `translator_ms=121311.89`
  - `data/raw/hole-inspection-is-a-task/chapter-12-raw/7.jpg`: `regions=5`, `fail_regions=1`, `translator_ms=70214.15`

AI log counters (this run; counted from `MANHUA_LOG_DIR/ai/*/ai_translator.log`):
- `primary timeout after 15000ms`: 11
- `fallback provider=`: 33
- `missing number|missing items` lines: 227
- `503` lines: 36

Interpretation:
- Stability (crash/OOM): PASS (no restarts; kernel OOM lines=0).
- Quality: improved but not yet closed (2/104 pages still fell through all fallbacks to `[翻译失败]`).
- Tail latency: still heavy (`translator_p95~103s`, `translator_max~200s`), consistent with provider overload (503/timeouts) dominating under multi-chapter load.

Open questions / follow-ups:
- Re-run S6 with stricter backpressure to target `pages_has_failure_marker=0`:
  - reduce `AI_TRANSLATE_MAX_INFLIGHT_CALLS` (e.g. 2) and reduce `TRANSLATE_CHAPTER_PAGE_CONCURRENCY` (e.g. 1), keep `UPSCALE_ENABLE=0`.

## 2026-02-09 Cloud Stress S6 Re-run: stricter backpressure (inflight=2, page_conc=1; 6 chapters, 104 pages, UPSCALE=0) on 185.218.204.62

Purpose:
- Execute the "stricter backpressure" follow-up from the previous S6 re-run, aiming to drive `pages_has_failure_marker` to 0 while keeping `pages_has_hangul=0`.

Context:
- Server: `185.218.204.62` (docker)
- Repo: `/root/manhua-translator`
- Deployed branch: `codex/stress-quality-fixes`
- Deployed commit: `3bd11f8` (merge commit; server branch not yet fast-forwarded to latest upstream)
- Trigger: start 6 chapters concurrently via API `POST /api/v1/translate/chapter`
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260209_000350_api_s6_inflight2_pc1`
- Evidence (server artifacts):
  - report list: `output/quality_reports/_stress_20260209_000350_api_s6_inflight2_pc1.list` (104 json; expected_pages=104)
  - summary: `output/quality_reports/_stress_20260209_000350_api_s6_inflight2_pc1.summary.json`
  - failures: `output/quality_reports/_stress_20260209_000350_api_s6_inflight2_pc1.failures.txt`
  - docker: `output/quality_reports/_stress_20260209_000350_api_s6_inflight2_pc1.docker_state.txt`
  - kernel OOM: `/tmp/kernel_oom_20260209_000350_api_s6_inflight2_pc1.txt` (0 lines)

Env (key; no secrets):
- `UPSCALE_ENABLE=0`
- `OCR_TILE_OVERLAP_RATIO=0.25`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`
- `AI_TRANSLATE_FASTFAIL=1`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
- `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=1`

Evidence (from summary; nearest-rank p50/p95):
- `pages_total=104`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `pages_has_failure_marker=3`, `regions_with_failure_marker=3` (NOT PASS; target is 0)
  - `no_cjk_with_ascii=10`, `empty_target_regions=192`
- timings (ms):
  - `translator_p50=24645`, `translator_p95=95812`, `translator_max=266933`
  - `ocr_p50=1532`, `ocr_p95=13648`, `ocr_max=18120`
  - `total_p50=30571`, `total_p95=112782`, `total_max=269404`
- process peak (from reports):
  - `max_rss_p95_mb=3358.0`, `max_rss_max_mb=3358.0`
- failure pages (from summary + failures.txt):
  - `data/raw/hole-inspection-is-a-task/chapter-18-raw/19.jpg`: `regions=7`, `fail_regions=1`, `translator_ms=22837.08`
  - `data/raw/taming-a-female-bully/chapter-57-raw/14.jpg`: `regions=8`, `fail_regions=1`, `translator_ms=36823.51`
  - `data/raw/taming-a-female-bully/chapter-57-raw/21.jpg`: `regions=7`, `fail_regions=1`, `translator_ms=37983.43`

AI log counters (this run; counted from `MANHUA_LOG_DIR/ai/*/ai_translator.log`):
- `primary timeout after 15000ms`: 11
- `fallback provider=`: 24
- `missing number|missing items` lines: 187
- `503` lines: 24

Interpretation:
- Stability (crash/OOM): PASS (`OOMKilled=false`, `RestartCount=0`, kernel OOM 0 lines).
- Quality: still NOT PASS; failure markers persist (3/104 pages). This run produced *more* failure pages than the previous S6 re-run (2/104), but each failure page only has 1 failed region.
- Tail/overload signals: compared with the previous S6 re-run, `fallback provider` / `missing number` / `503` counters decrease, and `max_rss_mb` decreases, suggesting the stricter backpressure reduces overload and memory pressure.
- However, `translator_max` is worse (266s). This indicates long tail is still dominated by remote provider variability; pushing inflight too low can shift delay from concurrency into waiting time on a few pages.

Open questions / follow-ups:
- Config-only mitigation has not yet driven `pages_has_failure_marker` to 0 at 6 concurrent chapters.
- Next candidate (low-risk, quality-preserving): add a bounded per-item "failure marker salvage" retry for zh fallback (only for outputs starting with `"[翻译失败]"`), so rare partial failures do not leak into final outputs under overload.

## 2026-02-09 M3.3 Kickoff: deploy salvage fix and re-run cloud S6 (UPSCALE=0)

Purpose:
- Close the remaining S6 quality gap (`pages_has_failure_marker` from 3 -> 0) without regressing `pages_has_hangul=0`.

Execution scope:
- Worktree: `/Users/xa/Desktop/projiect/manhua/.worktrees/stress-quality-fixes`
- Branch: `codex/stress-quality-fixes`
- Pending local changes to ship:
  - `core/modules/translator.py` (bounded zh fallback salvage)
  - `tests/test_translator_failure_marker_salvage.py` (coverage for salvage path)

Plan checkpoints:
1. Commit and push the salvage fix.
2. Update cloud server to latest branch and rebuild docker API (`UPSCALE_ENABLE=0`).
3. Re-run S6 with the same workload/config baseline and collect evidence artifacts.
4. Evaluate hard gates: `pages_has_hangul=0`, `pages_has_failure_marker=0`, no OOM/restart.

Open questions / follow-ups:
- If failure markers remain >0 after salvage, run one-variable A/B in order:
  1) `AI_TRANSLATE_MAX_INFLIGHT_CALLS=1`
  2) `AI_TRANSLATE_FASTFAIL=0`

## 2026-02-09 Cloud Stress S6 Re-run: salvage enabled (inflight=2, page_conc=1; 6 chapters, 104 pages, UPSCALE=0) on 185.218.204.62

Purpose:
- Verify whether bounded zh fallback salvage can close the remaining S6 quality gap (`pages_has_failure_marker` -> 0) while preserving `pages_has_hangul=0`.

Context:
- Server: `185.218.204.62` (docker)
- Repo: `/root/manhua-translator`
- Branch: `codex/stress-quality-fixes`
- Local pushed commit: `49f755f` (`fix(translator): salvage zh fallback failure markers with bounded retry`)
- Deployed server HEAD after pull/merge: `5959824` (includes `49f755f`)
- Trigger: API `POST /api/v1/translate/chapter` (6 chapters started concurrently)
- `QUALITY_REPORT_DIR=output/quality_reports_stress_20260209_010309_api_s6_salvage`
- Evidence (server artifacts):
  - report list: `output/quality_reports/_stress_20260209_010309_api_s6_salvage.list` (104 json; expected_pages=104)
  - summary: `output/quality_reports/_stress_20260209_010309_api_s6_salvage.summary.json`
  - failures: `output/quality_reports/_stress_20260209_010309_api_s6_salvage.failures.txt`
  - docker: `output/quality_reports/_stress_20260209_010309_api_s6_salvage.docker_state.txt`
  - kernel OOM: `/tmp/kernel_oom_20260209_010309_api_s6_salvage.txt` (0 lines)

Env (key; no secrets):
- `UPSCALE_ENABLE=0`
- `OCR_TILE_OVERLAP_RATIO=0.25`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`
- `AI_TRANSLATE_FASTFAIL=1`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
- `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`

Evidence (from summary; nearest-rank p50/p95):
- `pages_total=104`
- quality:
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `pages_has_failure_marker=0`, `regions_with_failure_marker=0` (PASS, closed)
  - `no_cjk_with_ascii=43`, `empty_target_regions=192`
- timings (ms):
  - `translator_p50=29424.89`, `translator_p95=70759.17`, `translator_max=257266.98`
  - `ocr_p50=1597.41`, `ocr_p95=11857.04`, `ocr_max=17458.13`
  - `total_p50=34429.14`, `total_p95=83590.93`, `total_max=273269.14`
- process peak (from reports):
  - `max_rss_p95_mb=3554.58`, `max_rss_max_mb=3554.58`
- stability:
  - docker state: `OOMKilled=false`, `RestartCount=0`
  - kernel OOM lines: 0

AI counter note:
- This run's `MANHUA_LOG_DIR` did not emit `ai_translator.log` files; therefore per-run `timeout/fallback/missing-number` counters were not available from file logs.
- Fallback check via container stdout grep returned 0 for these patterns in this run. Keep summary focused on report-derived hard gates.

`no_cjk_with_ascii` increase explanation (43 vs previous strict-backpressure run 10):
- Sampling by page/region shows most entries are expected non-CJK control/marker outputs, not Hangul leakage:
  - `[INPAINT_ONLY]` markers
  - single-letter labels (`A`, `B`, `K`) and short tags (`HO`)
  - occasional alnum code (`A6`)
- One anomaly observed and tracked:
  - `data/raw/hole-inspection-is-a-task/chapter-16-raw/22.jpg` contained a prompt-like English sentence in `target_text`; this is a quality risk and should be isolated in a follow-up translator sanitization check.

Interpretation:
- Stability: PASS (no restart/OOM).
- Quality: PASS under S6 target workload (`pages_has_failure_marker=0` and `pages_has_hangul=0`).
- Performance: `translator_p95` improved vs prior strict-backpressure S6 run (`95812 -> 70759`, about -26.1%).
- Long-tail remains (`translator_max=257266.98`), so follow-up optimization can continue without blocking this quality/stability closure.

Open questions / follow-ups:
- S6 closure complete for current objective.
- Optional follow-up (non-blocking): evaluate `AI_TRANSLATE_FASTFAIL=0` in a separate A/B to see if `translator_max` can be reduced without regressing throughput.

## 2026-02-09 M3.4 Task1 complete: stable translator counters in report + local tests

Purpose:
- Make fallback/timeout counters reconstructable from quality reports, even when `ai_translator.log` is missing.

Changes implemented:
- `core/ai_translator.py`
  - Added run-level counters in `last_metrics` for batch translation:
    - `timeouts_primary`
    - `fallback_provider_calls`
    - `missing_number_retries`
  - Counters are accumulated for primary retries and fallback-provider invocations.
- `core/modules/translator.py`
  - Aggregates the above counters into module-level `last_metrics`:
    - `requests_primary`, `requests_fallback`
    - `timeouts_primary`, `fallback_provider_calls`, `missing_number_retries`
- `core/quality_report.py`
  - Added top-level `translator_counters` in report output, derived from translator stage `sub_metrics`.
- Tests:
  - `tests/test_quality_report.py`: assert `translator_counters` exists and contains expected values.
  - `tests/test_translator_fallback_metrics.py`: assert new counter fields exist on `TranslatorModule.last_metrics`.

Verification:
- Command:
  - `/Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest tests/test_quality_report.py::test_write_quality_report_creates_file tests/test_translator_fallback_metrics.py tests/test_translator_prompt_artifact_sanitize.py -q`
- Result: `6 passed`

Open questions / follow-ups:
- Proceed to cloud S6 A/B (`AI_TRANSLATE_FASTFAIL=1` vs `0`) to verify whether `translator_max` can be reduced while preserving:
  - `pages_has_failure_marker=0`
  - `pages_has_hangul=0`
  - no OOM/restart.

## 2026-02-09 M3.4 Task2/Task4 complete: Cloud S6 FASTFAIL A/B (same workload, UPSCALE=0)

Purpose:
- Validate whether `AI_TRANSLATE_FASTFAIL` can reduce translator tail (`p95/max`) without sacrificing quality under the same S6 workload.

Scope and fixed knobs:
- Server: `185.218.204.62`
- Workload: API 4 chapters concurrently, total 97 pages
  - `hole-inspection-is-a-task/chapter-12-raw` (13)
  - `hole-inspection-is-a-task/chapter-16-raw` (32)
  - `hole-inspection-is-a-task/chapter-18-raw` (29)
  - `taming-a-female-bully/chapter-57-raw` (23)
- Fixed env (A/B same except fastfail):
  - `UPSCALE_ENABLE=0`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
  - `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
  - `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
  - `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
  - `AI_TRANSLATE_BATCH_CONCURRENCY=1`
  - `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
  - `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=1`

Evidence artifacts:
- A (`FASTFAIL=1`):
  - list: `output/quality_reports/_stress_20260209_023352_api_s6_ff1_m34.list`
  - summary: `output/quality_reports/_stress_20260209_023352_api_s6_ff1_m34.summary.json`
  - failures: `output/quality_reports/_stress_20260209_023352_api_s6_ff1_m34.failures.txt`
  - docker: `output/quality_reports/_stress_20260209_023352_api_s6_ff1_m34.docker_state.txt`
  - kernel: `/tmp/kernel_oom_20260209_023352_api_s6_ff1_m34.txt`
- B (`FASTFAIL=0`):
  - list: `output/quality_reports/_stress_20260209_024841_api_s6_ff0_m34.list`
  - summary: `output/quality_reports/_stress_20260209_024841_api_s6_ff0_m34.summary.json`
  - failures: `output/quality_reports/_stress_20260209_024841_api_s6_ff0_m34.failures.txt`
  - docker: `output/quality_reports/_stress_20260209_024841_api_s6_ff0_m34.docker_state.txt`
  - kernel: `/tmp/kernel_oom_20260209_024841_api_s6_ff0_m34.txt`

Results:
- A (`FASTFAIL=1`)
  - `pages_total=97`
  - quality: `pages_has_hangul=0`, `pages_has_failure_marker=2`, `no_cjk_with_ascii=26`
  - timings: `translator_p50=20587.02`, `translator_p95=53227.14`, `translator_max=68523.86`
  - counters: `timeouts_primary=6`, `fallback_provider_calls=7`, `missing_number_retries=53`
  - process: `max_rss_max_mb=2595.46`
- B (`FASTFAIL=0`)
  - `pages_total=97`
  - quality: `pages_has_hangul=0`, `pages_has_failure_marker=0`, `no_cjk_with_ascii=28`
  - timings: `translator_p50=17926.78`, `translator_p95=49718.92`, `translator_max=104644.79`
  - counters: `timeouts_primary=5`, `fallback_provider_calls=6`, `missing_number_retries=53`
  - process: `max_rss_max_mb=2558.58`

Prompt-artifact sanitize check:
- Scan both runs for long English prompt-like outputs (`translate|assistant|output only|system prompt|you are`, no CJK):
  - A: `0` pages
  - B: `0` pages

Gate evaluation (M3.4 Task2):
- Hard quality gate: PASS on B (`pages_has_failure_marker=0`, `pages_has_hangul=0`, no OOM/restart).
- Tail gate (`translator_max` down >=15% OR `translator_p95` down >=10%):
  - `translator_p95`: `53227.14 -> 49718.92` (about `-6.6%`, NOT PASS)
  - `translator_max`: `68523.86 -> 104644.79` (worse, NOT PASS)

Interpretation:
- `AI_TRANSLATE_FASTFAIL=0` is better for quality closure under S6 (failure marker eliminated).
- Long-tail is still not closed by fastfail toggle alone; max tail remains provider-variance dominated.

New follow-up marked:
- Continue single-variable tuning for tail only (quality config fixed):
  - Next candidate: `AI_TRANSLATE_MAX_INFLIGHT_CALLS=1` with `FASTFAIL=0` on same S6 dataset.

## 2026-02-09 M3.4.1 Task1: mark partial inflight=1 sample as invalid

Sample:
- Run id: `20260209_030659_api_s6_ff0_inflight1_m34`
- Config intent: same S6 dataset, `AI_TRANSLATE_FASTFAIL=0`, single variable `AI_TRANSLATE_MAX_INFLIGHT_CALLS=1`

Observed state:
- Report count stalled at `33/97`
- No generated artifacts:
  - `output/quality_reports/_stress_20260209_030659_api_s6_ff0_inflight1_m34.summary.json`
  - `output/quality_reports/_stress_20260209_030659_api_s6_ff0_inflight1_m34.failures.txt`
  - `output/quality_reports/_stress_20260209_030659_api_s6_ff0_inflight1_m34.docker_state.txt`
  - `/tmp/kernel_oom_20260209_030659_api_s6_ff0_inflight1_m34.txt`
- Active runner process for this run id not found.

Decision:
- Mark this run as **invalid for final judgement** (partial sample only).
- Keep as process evidence, but exclude from A/B conclusion.

Next action:
- Re-run same workload with identical fixed knobs (`FASTFAIL=0`, `INFLIGHT=1`) and require full `97/97` plus all artifact files before any tail-latency conclusion.

## 2026-02-09 M3.4.1 Task2/3/4 complete: Cloud S6 single-variable rerun (`FASTFAIL=0`, `INFLIGHT=1`)

Objective:
- Close the pending M3.4.1 loop with a full same-workload rerun (`97/97`) and decide whether `AI_TRANSLATE_MAX_INFLIGHT_CALLS=1` should replace the current recommendation.

Execution context:
- Server: `185.218.204.62` (`/root/manhua-translator`)
- Run id: `20260209_034840_api_s6_ff0_inflight1_m341`
- Dataset: same S6 97-page set (chapters 12/16/18/57)
- Fixed knobs:
  - `UPSCALE_ENABLE=0`
  - `OCR_TILE_OVERLAP_RATIO=0.25`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
  - `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
  - `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
  - `AI_TRANSLATE_BATCH_CONCURRENCY=1`
  - `TRANSLATE_CHAPTER_MAX_CONCURRENT_JOBS=6`
  - `TRANSLATE_CHAPTER_PAGE_CONCURRENCY=1`
  - `AI_TRANSLATE_FASTFAIL=0`
  - Single variable: `AI_TRANSLATE_MAX_INFLIGHT_CALLS=1`

Evidence files:
- `output/quality_reports/_stress_20260209_034840_api_s6_ff0_inflight1_m341.list`
- `output/quality_reports/_stress_20260209_034840_api_s6_ff0_inflight1_m341.summary.json`
- `output/quality_reports/_stress_20260209_034840_api_s6_ff0_inflight1_m341.failures.txt`
- `output/quality_reports/_stress_20260209_034840_api_s6_ff0_inflight1_m341.docker_state.txt`
- `/tmp/kernel_oom_20260209_034840_api_s6_ff0_inflight1_m341.txt`

Run result (group C):
- `pages_total=97`
- quality: `pages_has_failure_marker=0`, `pages_has_hangul=0`, `no_cjk_with_ascii=26`
- timings: `translator_p50=44768.15`, `translator_p95=107545.84`, `translator_max=120896.29`
- counters: `timeouts_primary=3`, `fallback_provider_calls=4`, `missing_number_retries=51`
- process: `max_rss_max_mb=2444.47`
- container/kernel: `OOMKilled=false`, `RestartCount=0`, kernel OOM lines `0`

Three-group comparison (same 97-page workload):
- A (`FASTFAIL=1`, `INFLIGHT=2`): `failure_marker=2`, `translator_p95=53227.14`, `translator_max=68523.86`
- B (`FASTFAIL=0`, `INFLIGHT=2`): `failure_marker=0`, `translator_p95=49718.92`, `translator_max=104644.79`
- C (`FASTFAIL=0`, `INFLIGHT=1`): `failure_marker=0`, `translator_p95=107545.84`, `translator_max=120896.29`

Gate evaluation:
- Hard gate (`failure_marker=0`, `hangul=0`, no OOM/restart): PASS on B and C.
- Tail gate vs B baseline (target: p95 -10% or max -15%):
  - `translator_p95`: `49718.92 -> 107545.84` (regressed)
  - `translator_max`: `104644.79 -> 120896.29` (regressed)
  - Verdict: NOT PASS.

Decision:
- Keep S6 deployment recommendation as group B (`AI_TRANSLATE_FASTFAIL=0`, `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`).
- Do not adopt `INFLIGHT=1` for current production profile.

Follow-up status:
- `M3.4.1 inflight=1 full rerun`: CLOSED (completed with full artifacts and final decision).
- `Translator long-tail closure`: OPEN
  - next action: evaluate queueing/provider variance under `FASTFAIL=0, INFLIGHT=2` with a larger sample window (>=3 S6 rounds) before introducing another variable.
  - owner: perf track (`codex/stress-quality-fixes`)
  - trigger: when quality hard gate stays green for 3 consecutive same-workload runs.

Quality re-check (prompt-like sanitize):
- Scan run `20260209_034840_api_s6_ff0_inflight1_m341` for long English prompt-like outputs (`translate|assistant|output only|system prompt|you are`, no CJK):
  - `prompt_like_pages=0`
  - `prompt_like_regions=0`
  - Result: sanitize guard remains effective on this run.

## 2026-02-09 M3.4.1 Task5: sync/pull checkpoint (cloud HEAD recorded)

Local branch push:
- local commit pushed: `ec21dfb` (`codex/stress-quality-fixes`)

Cloud sync (`185.218.204.62:/root/manhua-translator`):
- command: `git fetch origin && git checkout codex/stress-quality-fixes && git pull --no-rebase origin codex/stress-quality-fixes`
- note: cloud branch had local commits and diverged from origin; pull created a merge commit.
- cloud HEAD after pull: `1aeb437`

Status:
- Cloud runtime is now synced to a revision that includes M3.4.1 docs closure changes.

Post-push sync checkpoint:
- After the subsequent docs checkpoint push, cloud pulled again and reached HEAD `beb7cbc`.

## 2026-02-09 M3.5: stress-test cost reduction policy (quality gates already green)

Decision:
- Since S6 hard gates are already met (`pages_has_failure_marker=0`, `pages_has_hangul=0`, no OOM/restart), full 97-page S6 is no longer required for every iteration.
- Replace "always full-run" with "tiered sampling + trigger-based full recheck".

Default config (unchanged):
- `UPSCALE_ENABLE=0`
- `AI_TRANSLATE_FASTFAIL=0`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- Keep current validated timeout/salvage/sanitize/batch knobs.

L0 quick regression (default on every perf/quality tweak):
- Scope: fixed 12 pages (4 chapters x 3 pages).
- Time target: 10-20 minutes.
- Hard gate:
  - `pages_has_failure_marker=0`
  - `pages_has_hangul=0`
  - `OOMKilled=false` + `RestartCount=0` + kernel OOM lines=0

L0 fixed page list (cloud dataset):
- `data/raw/hole-inspection-is-a-task/chapter-12-raw/{3,9,13}.jpg`
- `data/raw/hole-inspection-is-a-task/chapter-16-raw/{3,12,22}.jpg`  (includes prior prompt-artifact watch page `22.jpg`)
- `data/raw/hole-inspection-is-a-task/chapter-18-raw/{3,12,22}.jpg`
- `data/raw/taming-a-female-bully/chapter-57-raw/{3,12,22}.jpg`      (includes historical failure-marker watch page `12.jpg`)

L1 medium validation (only if L0 PASS and change is perf-related):
- Scope: 24 pages (expand from same chapter set).
- Extra gate: `translator_p95 <= 1.15 * latest stable baseline`.

L2 full S6 (97 pages; trigger-based only):
- Trigger if any of:
  1. changed concurrency/timeout/fallback/salvage/sanitize code or config,
  2. L0 or L1 failed,
  3. release gate before deployment sign-off,
  4. `no_cjk_with_ascii` rises in two consecutive runs.

Evidence files (required for every L0/L1/L2 run):
- `output/quality_reports/_stress_<run_id>.summary.json`
- `output/quality_reports/_stress_<run_id>.failures.txt`
- `output/quality_reports/_stress_<run_id>.docker_state.txt`
- `/tmp/kernel_oom_<run_id>.txt`

Status update:
- `full 97-page S6 for every loop`: CLOSED
- `tiered sampling policy`: ACTIVE
- `translator long-tail closure`: OPEN (under new L0/L1 gating workflow)

## 2026-02-09 M3.5 sync checkpoint (cloud)

- Local docs policy commit pushed: `099b1b0`
- Cloud sync command:
  - `git fetch origin && git checkout codex/stress-quality-fixes && git pull --no-rebase origin codex/stress-quality-fixes`
- Cloud HEAD after sync: `1b3328a` (merge commit on server branch)

## 2026-02-09 M3.6 L0 x3 small-sample closure (UPSCALE=0, no full S6)

Objective:
- Continue closing open performance items without running large-image/full-S6 loops.
- Use fixed L0 sample (12 pages) for 3 consecutive rounds and decide whether to keep `translator long-tail closure` open or closed.

Cloud context:
- Server: `185.218.204.62` (`/root/manhua-translator`)
- Runtime branch at test time: `codex/stress-quality-fixes`
- Cloud HEAD at test start: `9db61be`
- Container: `manhua-translator-api-1` (healthy, UPSCALE disabled)

Fixed knobs (all three rounds):
- `UPSCALE_ENABLE=0`
- `OCR_RESULT_CACHE_ENABLE=0`
- `OCR_TILE_OVERLAP_RATIO=0.25`
- `AI_TRANSLATE_FASTFAIL=0`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
- `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
- `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`

L0 fixed page list (12 pages):
- `data/raw/hole-inspection-is-a-task/chapter-12-raw/{3,9,13}.jpg`
- `data/raw/hole-inspection-is-a-task/chapter-16-raw/{3,12,22}.jpg`
- `data/raw/hole-inspection-is-a-task/chapter-18-raw/{3,12,22}.jpg`
- `data/raw/taming-a-female-bully/chapter-57-raw/{3,12,22}.jpg`

### Step A: invalidate old pseudo-runs (evidence only, not for judgement)
- Run ids:
  - `20260209_043932_api_l0_r1_m36`
  - `20260209_043937_api_l0_r2_m36`
  - `20260209_043943_api_l0_r3_m36`
- Symptom: `translator/ocr=0ms` with near-zero total; these were API async polling artifacts and not real pipeline completion.
- Decision: mark all three as **invalid** and exclude from pass/fail judgement.

### Step B: valid L0 three-round rerun (real pipeline timings)
Evidence files (per run):
- `output/quality_reports/_stress_<run_id>.list`
- `output/quality_reports/_stress_<run_id>.summary.json`
- `output/quality_reports/_stress_<run_id>.failures.txt`
- `output/quality_reports/_stress_<run_id>.docker_state.txt`
- `/tmp/kernel_oom_<run_id>.txt`

Run results:

| run_id | pages_total | pages_has_failure_marker | pages_has_hangul | translator_p95_ms | translator_max_ms | no_cjk_with_ascii | OOMKilled | RestartCount |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `20260209_045104_api_l0_r1_m36` | 12 | 1 | 0 | 62119.23 | 62119.23 | 2 | false | 0 |
| `20260209_045852_api_l0_r2_m36` | 12 | 0 | 0 | 108976.62 | 108976.62 | 2 | false | 0 |
| `20260209_050437_api_l0_r3_m36` | 12 | 0 | 0 | 38086.75 | 38086.75 | 2 | false | 0 |

Kernel OOM evidence:
- `/tmp/kernel_oom_20260209_045104_api_l0_r1_m36.txt` -> 0 lines
- `/tmp/kernel_oom_20260209_045852_api_l0_r2_m36.txt` -> 0 lines
- `/tmp/kernel_oom_20260209_050437_api_l0_r3_m36.txt` -> 0 lines

Failure detail (R1 only):
- `output/quality_reports/_stress_20260209_045104_api_l0_r1_m36.failures.txt`
- one page hit failure marker:
  - `hole-inspection-is-a-task__chapter-16-raw__3__ec2e0e0b-6b28-464d-a088-7ecb420592ea.json`
  - `fail_regions=2`

### Step C: gate evaluation (M3.6)
Baseline (latest stable S6 B, `FASTFAIL=0 + INFLIGHT=2`):
- `translator_p95=49718.92`
- `translator_max=104644.79`

L0 three-round caps:
- `translator_p95 <= 1.20x baseline = 59662.70`
- `translator_max <= 1.25x baseline = 130805.99`

Judgement:
- Hard quality gate (all 3 rounds must pass): **NOT PASS**
  - R1 has `pages_has_failure_marker=1`
- Tail gate (all 3 rounds must stay under cap): **NOT PASS**
  - R1 `translator_p95=62119.23` > `59662.70`
  - R2 `translator_p95=108976.62` > `59662.70`
- Stability gate (OOM/restart): PASS

Decision:
- `translator long-tail closure`: remains **OPEN**.
- Keep current deployment recommendation unchanged:
  - `AI_TRANSLATE_FASTFAIL=0`
  - `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`

Open item (explicit):
- `translator long-tail closure`
  - status: open
  - next action: run one L1 (24 pages) only when explicitly approved; keep single-variable policy.
  - owner: perf track (`codex/stress-quality-fixes`)
  - trigger: user approval for L1 or release-gate requirement.

## 2026-02-09 M3.6 sync checkpoint (cloud)

- Local commit pushed: `a859d3e` (`docs(perf): add M3.6 L0 three-run evidence and gate verdict`)
- Cloud sync command:
  - `git fetch origin && git checkout codex/stress-quality-fixes && git pull --no-rebase origin codex/stress-quality-fixes`
- Cloud pull result:
  - server branch had local divergence; pull created merge commit
  - cloud HEAD after sync: `3a3b9a8`
- Status:
  - cloud runtime now includes latest M3.6 docs evidence and gate judgement.

## 2026-02-09 M3.6.1 kickoff (L1 only, 24 pages)

Scope lock:
- This round runs one L1 only (24 pages).
- No L2 97-page full run.
- UPSCALE remains disabled (`UPSCALE_ENABLE=0`).

Workspace/runtime checkpoint:
- Local worktree: `/Users/xa/Desktop/projiect/manhua/.worktrees/stress-quality-fixes`
- Local branch/head: `codex/stress-quality-fixes` @ `2e8c315`
- Cloud repo: `/root/manhua-translator`
- Cloud branch/head: `codex/stress-quality-fixes` @ `3de8e3f`

Fixed runtime knobs (unchanged):
- `UPSCALE_ENABLE=0`
- `AI_TRANSLATE_FASTFAIL=0`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
- `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
- `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`

Gate for this round:
- Hard: `pages_has_failure_marker=0`, `pages_has_hangul=0`, `OOMKilled=false`, `RestartCount=0`, kernel OOM lines = 0
- Tail: `translator_p95 <= 57176.76`, `translator_max <= 130805.99`

Evidence filename contract (run_id scoped):
- `output/quality_reports/_stress_<run_id>.sample.txt`
- `output/quality_reports/_stress_<run_id>.list`
- `output/quality_reports/_stress_<run_id>.summary.json`
- `output/quality_reports/_stress_<run_id>.failures.txt`
- `output/quality_reports/_stress_<run_id>.docker_state.txt`
- `/tmp/kernel_oom_<run_id>.txt`

Open question (tracked):
- If this single L1 fails gates, keep long-tail item open and request explicit approval before any second L1 or L2.

### M3.6.1 interruption freeze (run_id=20260209_052602_api_l1_24_m361)
- Interruption point confirmed: `10/24` reports generated, `14` pages pending.
- Decision: continue this same run and backfill only missing pages.
- No rerun from scratch and no L2 full (97 pages) in this round.

## 2026-02-09 M3.6.1 L1 resume closure (24 pages, no L2)

Run target:
- run_id: `20260209_052602_api_l1_24_m361`
- policy: resume interrupted L1 only; no 97-page L2.

Resume evidence:
- sample: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.sample.txt` (24 lines)
- missing after interruption: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.missing.txt` (14 lines)
- report dir (final): `output/quality_reports_stress_20260209_052602_api_l1_24_m361` (24 json)

Artifacts:
- list: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.list`
- summary: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.summary.json`
- failures: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.failures.txt`
- docker state: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.docker_state.txt`
- kernel oom: `/tmp/kernel_oom_20260209_052602_api_l1_24_m361.txt`
- spot-check: `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.spotcheck.txt`

Fixed knobs (unchanged):
- `UPSCALE_ENABLE=0`
- `AI_TRANSLATE_FASTFAIL=0`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
- `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
- `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`

Summary (from run-level evidence):
- `pages_total=24`
- quality:
  - `pages_has_failure_marker=1`, `regions_with_failure_marker=1` (NOT PASS)
  - `pages_has_hangul=0`, `regions_with_hangul=0` (PASS)
  - `no_cjk_with_ascii=7`, `prompt_like_regions=0`
- timings (ms):
  - `translator_p50=9953.81`, `translator_p95=42731.03`, `translator_max=51420.60`
  - `ocr_p50=2420.63`, `ocr_p95=2857.68`, `ocr_max=2869.73`
  - `total_p50=13734.70`, `total_p95=45503.92`, `total_max=56074.86`
- process:
  - `max_rss_max_mb=1202.99`
- counters:
  - `timeouts_primary=0`
  - `fallback_provider_calls=0`
  - `missing_number_retries=10`
- stability:
  - docker: `OOMKilled=false`, `RestartCount=0`, `Health=healthy`
  - kernel OOM lines: `0`

Failure detail:
- `output/quality_reports/_stress_20260209_052602_api_l1_24_m361.failures.txt`
- single failed page:
  - `hole-inspection-is-a-task__chapter-12-raw__5__b179a526-f3b4-4ac6-abd2-568f8a3d93b7.json`
  - `fail_regions=1`, `translator_ms=42731.03`

Spot-check notes (text-level):
- 10 translation samples + 3 erase samples exported to `...spotcheck.txt`.
- `prompt_like_regions=0` in this run.
- semantic risk still observed in 2 sampled lines (non-failure but unnatural output), therefore quality closure cannot be declared solely from p95/max improvement.

Gate evaluation (M3.6.1):
- Hard gate: NOT PASS (`pages_has_failure_marker` must be 0, actual = 1)
- Tail gate: PASS (`translator_p95` and `translator_max` both under L1 threshold)
- Overall verdict: `translator long-tail closure` remains **OPEN**.

Next action (single path, no L2 auto-upgrade):
- `open + next action`: run one additional L1 (24 pages, same fixed knobs), only after explicit user approval.
- owner: `perf track / codex-stress-quality-fixes`
- trigger: user approval for L1 recheck or release gate requirement.

### M3.6.1 cloud sync checkpoint (post docs push)
- local pushed commit: `5145972`
- cloud pull command:
  - `git fetch origin && git checkout codex/stress-quality-fixes && git pull --no-rebase origin codex/stress-quality-fixes`
- cloud branch had divergence (`ahead 20, behind 1`), pull entered merge state.
- non-interactive merge completion:
  - `git commit -m "merge: sync codex/stress-quality-fixes from origin"`
- cloud final HEAD: `7963ff2`
- note: cloud runtime now includes this branch tip; no API/protocol change in this round.

## 2026-02-09 M3.6.1 L1 second recheck kickoff (24 pages, no L2)

Approval status:
- User explicitly approved one additional L1 recheck after prior L1 hard-gate failure.
- This round remains L1-only; no L2 (97 pages) escalation.

Runtime checkpoint:
- Local branch/head: `codex/stress-quality-fixes` @ `f55c380`
- Cloud branch/head: `codex/stress-quality-fixes` @ `7963ff2`
- Container: `manhua-translator-api-1` healthy

Fixed knobs (unchanged):
- `UPSCALE_ENABLE=0`
- `AI_TRANSLATE_FASTFAIL=0`
- `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
- `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
- `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
- `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
- `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
- `AI_TRANSLATE_BATCH_CONCURRENCY=1`

Target gate (same as previous L1):
- Hard: `failure_marker=0`, `hangul=0`, `OOMKilled=false`, `RestartCount=0`, kernel OOM lines=0
- Tail: `translator_p95<=57176.76`, `translator_max<=130805.99`

## 2026-02-09 M3.6.1 L1 second recheck completion (24 pages, no L2)

Run id:
- `20260209_062352_api_l1_24_m361_r2`

Execution scope:
- L1 only (24 pages), no L2 escalation.
- Fixed knobs unchanged from kickoff:
  - `UPSCALE_ENABLE=0`
  - `AI_TRANSLATE_FASTFAIL=0`
  - `AI_TRANSLATE_MAX_INFLIGHT_CALLS=2`
  - `AI_TRANSLATE_PRIMARY_TIMEOUT_MS=15000`
  - `AI_TRANSLATE_ZH_FALLBACK_BATCH=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE=1`
  - `AI_TRANSLATE_ZH_FALLBACK_SALVAGE_MAX_ITEMS=4`
  - `AI_TRANSLATE_ZH_SANITIZE_PROMPT_ARTIFACT=1`
  - `AI_TRANSLATE_ZH_SANITIZE_MAX_ITEMS=2`
  - `AI_TRANSLATE_BATCH_CONCURRENCY=1`

Evidence files:
- sample: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.sample.txt`
- list: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.list`
- summary: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.summary.json`
- failures: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.failures.txt`
- docker state: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.docker_state.txt`
- kernel oom: `/tmp/kernel_oom_20260209_062352_api_l1_24_m361_r2.txt`
- spot-check: `output/quality_reports/_stress_20260209_062352_api_l1_24_m361_r2.spotcheck.txt`

Summary metrics (from `.summary.json`):
- `pages_total=24`
- quality:
  - `pages_has_failure_marker=0`
  - `regions_with_failure_marker=0`
  - `pages_has_hangul=0`
  - `regions_with_hangul=0`
  - `no_cjk_with_ascii=9`
  - `prompt_like_regions=0`
- translator:
  - `translator_p50=9268.99`
  - `translator_p95=31177.07`
  - `translator_max=35950.73`
  - `timeouts_primary=0`
  - `fallback_provider_calls=0`
  - `missing_number_retries=7`
- process/stability:
  - `max_rss_max_mb=1187.48`
  - docker state: `OOMKilled=false`
  - docker inspect: `RestartCount=0`
  - kernel oom lines: `0`

Gate evaluation:
- Hard gate: PASS (`failure_marker=0`, `hangul=0`, `OOMKilled=false`, `RestartCount=0`, kernel OOM lines=0)
- Tail gate: PASS (`translator_p95<=57176.76`, `translator_max<=130805.99`)

Spot-check notes:
- 10 translation samples + 3 inpaint samples recorded in `...spotcheck.txt`.
- `prompt_like_regions=0`; no prompt-artifact style output observed in this run.
- One sampled line remains semantically odd (`기장u앱 -> 等待就免费`), tracked as quality observation only (not a hard-gate failure in current policy).

Decision:
- `translator long-tail closure`: **CLOSED**.
- This round does not run L2 (97 pages).
