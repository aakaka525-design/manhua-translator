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
### Translator: retry on missing numbered items (reduce per-item fallback + tail)
Evidence:
- `logs/ai/20260208/ai_translator.log` contains repeated warnings like `AI response missing number 10/11/12`, which leads to empty translations for those items.
- Downstream then marks them as `[翻译失败] ...` and triggers per-item fallback calls, increasing remote calls and p95/p99 latency.

Change:
- In `core/ai_translator.py` `translate_batch()`: when numbered output is detected but some indices are missing (parsed as empty strings), retry the same batch immediately with:
  - stricter format instructions (must output exactly `1..N`), and
  - additional `max_tokens` headroom via env `AI_TRANSLATE_BATCH_MAX_TOKENS_MISSING_NUMBER_BONUS` (default 800).
- Add test: `tests/test_ai_translator.py::test_translate_batch_retries_when_numbered_output_missing_items`.

Open questions:
- Should we add similar retry logic for `output_format=json` when JSON extraction returns fewer than expected items (partial/malformed)? Current fix targets the dominant numbered-output truncation case.

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
- Is 15000ms the best tradeoff across W2 (chapter, concurrency)? Need additional sampling on W2 to confirm stability under concurrency.
- Should we consider 18000ms for extreme tail cases, or keep 15000ms as a safe default recommendation?

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
- W2 full chapter (9 pages) was NOT re-run under `15000ms` in this round (cost control). Keep as an optional follow-up sampling before promoting the recommendation broadly in production.

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
