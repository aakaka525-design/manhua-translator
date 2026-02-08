# 08 M3 Plan (OCR + Translator Perf, Quality-Guarded)

Date: 2026-02-08
Worktree: `.worktrees/perf-m1-ocr-translator`
Branch: `codex/perf-m1-ocr-translator`

## Goals
- Reduce long-image end-to-end latency by focusing on OCR + Translator.
- Make Translator latency explainable: stage wall-time should be attributable to `TranslatorModule.last_metrics` (including fallbacks).
- Do not regress quality:
  - OCR recall/accuracy (regions count and spot-check).
  - Translation semantics/context (no increased mixed-language outputs).
  - Inpaint/repair quality (no increased missed/incorrect erase; spot-check).

## Fixed Workloads (M3 Input Set)
All M3 benchmarks must run with:
- `UPSCALE_ENABLE=0`
- `OCR_RESULT_CACHE_ENABLE=0`
- Record both cold-start and warm-start (run twice; use 2nd run for "warm" numbers).

Workloads:
- W1 (single page, short):
  - `/Users/xa/Desktop/projiect/manhua/data/raw/sexy-woman/chapter-1/15.jpg`
- W2 (chapter, fixed pages; use `-w 2`):
  - `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/` (9 pages)
- W3 (single long page, high text density):
  - `/Users/xa/Desktop/projiect/manhua/data/raw/wireless-onahole/chapter-68/9.jpg` (720x19152)

## Command Templates
Single page (W1/W3), warm run should be executed twice:
```bash
QUALITY_REPORT_DIR=output/quality_reports_m3 \
OCR_RESULT_CACHE_ENABLE=0 \
UPSCALE_ENABLE=0 \
/Users/xa/Desktop/projiect/manhua/.venv/bin/python main.py image <img> -s korean -t zh -o /tmp/perf_m3_out
```

Chapter (W2), run once cold + once warm:
```bash
QUALITY_REPORT_DIR=output/quality_reports_m3 \
OCR_RESULT_CACHE_ENABLE=0 \
UPSCALE_ENABLE=0 \
/Users/xa/Desktop/projiect/manhua/.venv/bin/python main.py chapter <input_dir> /tmp/perf_m3_ch68 -w 2 -s korean -t zh
```

## M3 Acceptance Gates
### Performance (W3 primary)
- OCR duration: relative to M2 baseline (48s) improve >= 25% (target <= 36s).
- Translator duration: relative to M2 baseline (101s) improve >= 30% (target <= 70s).
- Explainability: Translator wall-time vs metrics gap <= 10% once fallback timers are added.

### Quality (hard guardrails)
- OCR regions count: must not drop vs baseline (84). Allow +-1 jitter only if explained in worklog with evidence (e.g., better dedupe).
- Translation quality: do not increase mixed-language outputs. Manually spot-check 10 translations on W3.
- Inpaint/repair: do not increase missed erase/incorrect erase on 3 sampled regions.

## A/B Knobs (M3)
Translator:
- `AI_TRANSLATE_ZH_FALLBACK_BATCH=0|1` (default 0)
  - 0: current per-item retranslate
  - 1: opt-in batch retranslate for zh fallback (reduce remote calls / tail latency)

OCR tiling (already env-driven in M2; defaults unchanged):
- `OCR_TILE_HEIGHT` (baseline: 1024)
- `OCR_TILE_OVERLAP_RATIO` (baseline: 0.5; known candidate: 0.25)
- `OCR_EDGE_TILE_MODE=off|on|auto`
- `OCR_SMALL_IMAGE_SCALE_MODE=always|auto|off`

## Worklog Rule (mandatory)
After each key step OR when a new question appears, append to:
- `docs/perf_audit/2026-02-08/06_worklog.md`

Record:
- exact command lines
- key stage durations
- `TranslatorModule.last_metrics` summary (including fallback timers once implemented)
- any quality anomalies and the investigation result

