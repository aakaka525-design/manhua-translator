# QualityGate Phase 2 Design (Record + Recommend)

Date: 2026-01-27
Project: manhua
Scope: Quality scoring + recommendations written into QualityReport JSON (no auto-retry)

## 1. Goal
Add region-level quality scoring and recommendations to QualityReport JSON. This phase only records signals and suggestions; it does not trigger retries or alter pipeline flow.

## 2. Decisions
- Mode: record + recommend only
- Thresholds: 0.75 / 0.55 (from existing design)
- Output: QualityReport JSON (not logs-only)
- Granularity: region-level
- Recommendation types (minimum):
  - retry_translation
  - review_glossary
  - check_overflow
  - low_ocr_confidence
- Recommendation priority order:
  retry_translation > low_ocr_confidence > check_overflow > review_glossary

## 3. Approach Options
A) Compute score/recommendations in quality_report writer (recommended)
B) Compute in Pipeline after result (store in context/result)
C) Compute in Translation module (more coupling)

Chosen: A, to keep changes minimal and avoid pipeline behavior changes.

## 4. Data Flow
Pipeline.process() -> PipelineResult -> write_quality_report(result)
- write_quality_report() performs per-region evaluation
- writes quality_score, quality_signals, recommendations into JSON
- no pipeline state changes

## 5. Quality Score
Formula (unchanged):
score = 0.35*ocr_conf + 0.25*length_fit + 0.20*glossary_cov + 0.10*punctuation_ok + 0.10*model_conf

Signals:
- ocr_conf: RegionData.confidence (default 0.5 if missing)
- length_fit:
  - 1 - min(1, abs(len(tgt)-target_len)/target_len)
  - if target_len missing: 0.5 (neutral)
- glossary_cov: coverage ratio; if glossary disabled/empty, set to 1.0
- punctuation_ok: simple heuristic (balanced quotes/brackets, no dangling punctuation)
- model_conf: 0.5 default (LLM confidence usually unavailable)

## 6. Recommendations
Trigger rules (region-level):
- retry_translation: quality_score < 0.55
- review_glossary: glossary_cov < 0.6
- check_overflow: length_fit < 0.7
- low_ocr_confidence: ocr_conf < 0.6

Ordering:
- Apply priority order when multiple triggers fire.

Edge cases:
- target_text missing: keep length_fit = 0.5 and still allow retry_translation
- source_text/confidence missing: ocr_conf = 0.5 and add low_ocr_confidence
- SFX regions: skip review_glossary

## 7. JSON Schema Changes (regions[])
Add fields per region:
- quality_score: number
- quality_signals: object
  - ocr_conf
  - length_fit
  - glossary_cov
  - punctuation_ok
  - model_conf
- recommendations: array of strings

Example:
{
  "region_id": "...",
  "source_text": "...",
  "target_text": "...",
  "quality_score": 0.62,
  "quality_signals": {
    "ocr_conf": 0.88,
    "length_fit": 0.5,
    "glossary_cov": 0.3,
    "punctuation_ok": 1,
    "model_conf": 0.5
  },
  "recommendations": ["review_glossary", "check_overflow"]
}

## 8. Implementation Notes
- Add evaluate_region_quality() inside core/quality_report.py
- Keep pipeline unchanged; only extend report generation
- Use existing data when possible; avoid new dependencies

## 9. Tests
- quality_signals correctness (including length_fit = 0.5 fallback)
- recommendation triggers
- recommendation ordering
- SFX skips review_glossary

## 10. Non-Goals
- Auto-retry or fallback model selection
- UI changes
- Performance optimization beyond simple caching
