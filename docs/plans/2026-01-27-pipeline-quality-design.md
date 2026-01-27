# Pipeline Quality-First Design (Manhua)

Date: 2026-01-27
Project: manhua
Focus: OCR -> Translation -> Inpainting -> Rendering quality improvements

## 1. Background
The current pipeline produces good results but has inconsistent translation quality, uneven typography, and limited control over style/terminology. We want a quality-first design that improves correctness, consistency, and bubble-fit while keeping the main pipeline flow intact.

## 2. Goals
- Improve translation quality and consistency across pages/chapters.
- Enforce bubble-size constraints to reduce overflow and awkward line breaks.
- Add structured quality scoring and fallback strategies.
- Keep changes incremental and backward-compatible with current modules.

## 3. Non-Goals
- Major UI rework.
- Replacing the OCR or inpainting engine entirely.
- Large-scale performance optimization (can be a later phase).

## 4. Proposed Architecture
Keep the 4-stage pipeline but add quality-focused sub-modules. Where possible, reuse existing logic rather than duplicating it.

- OCR
  - OCRPostProcessor: normalize text, fix common OCR errors, language-aware corrections (no semantic changes).
- Translation
  - BubbleGrouper: reuse existing group_adjacent_regions() (core/translator.py) as the base; extend only with reading order and bubble_id tagging.
  - ContextBuilder: build bounded context per bubble/page.
  - TranslationOrchestrator: glossary + character lexicon + length constraints.
  - QualityGate: score output and trigger retries/fallback models.
- Inpainting
  - unchanged; receives regions marked for render/skip.
- Rendering
  - LayoutEstimator: compute max_chars and layout constraints using the current renderer's sizing logic.
  - Renderer: respect max_chars and typography rules.

## 4.1 Mapping to Existing Code (Concrete)
- Pipeline orchestration: core/pipeline.py (add hooks to call quality helpers between stages).
- OCR stage: core/modules/ocr.py (call OCRPostProcessor after detect_and_recognize()).
- Region grouping: core/translator.py:group_adjacent_regions() (BubbleGrouper = wrapper + tagging).
- Translation stage: core/modules/translator.py + core/ai_translator.py (inject glossary/character rules and length limits in prompts).
- Rendering: core/modules/renderer.py + core/renderer.py (add LayoutEstimator helper near fit_text_to_box()).
- Data model updates: core/models.py.

## 5. Module Details (Concrete)
### 5.1 OCRPostProcessor (scope)
Purpose: clean OCR noise without changing meaning.
Inputs: RegionData.source_text, RegionData.confidence.
Outputs: normalized_text, is_sfx, optional ocr_notes.

Rules (minimal, safe):
- Normalize whitespace and punctuation (full-width/half-width).
- Fix common OCR confusions (e.g., O/0, l/1, rn/m) via language-specific maps.
- Remove control chars and stray artifacts.
- Tag SFX using existing _is_sfx() patterns and keep original text for rendering rules.

Where: invoked inside OCRModule.process() after detect_and_recognize() to avoid changing pipeline APIs.

### 5.2 BubbleGrouper (overlap resolution)
Use core/translator.py:group_adjacent_regions() as the single source of truth.
BubbleGrouper becomes a thin wrapper that:
- assigns bubble_id per group,
- computes reading_order (top-to-bottom, left-to-right by default),
- exposes group metadata to TranslationOrchestrator.

### 5.3 LayoutEstimator (details)
Goal: estimate capacity and layout constraints before translation and rendering.

Algorithm (uses existing renderer logic):
1) For each region box, compute available width/height with padding.
2) Use TextRenderer.fit_text_to_box() to test a synthetic string length and infer max_chars.
3) Convert to max_chars using avg character width at the chosen font size.
4) Record constraints: max_chars, max_lines, preferred_font_size_range.

Fallback heuristic (if font metrics unavailable):
- max_chars = floor((w / avg_char_w) * (h / line_height)), where
  avg_char_w ~= font_size * 0.9, line_height ~= font_size * 1.2.

## 6. Quality Score Definition (Concrete)
Define a normalized score in [0,1]. Suggested weights (tunable in config/quality.yml):

score = 0.35 * ocr_conf + 0.25 * length_fit + 0.20 * glossary_cov + 0.10 * punctuation_ok + 0.10 * model_conf

Signals:
- ocr_conf: existing RegionData.confidence (or avg per bubble).
- length_fit: 1 - min(1, abs(len(tgt)-target_len)/target_len) where target_len is from max_chars.
- glossary_cov: percentage of glossary terms matched.
- punctuation_ok: 1 if output is well-formed (no dangling quotes/ellipsis), else 0.
- model_conf: optional; 0.5 default if no confidence available.

Thresholds (initial):
- >= 0.75: accept
- 0.55-0.75: retry with concise prompt
- < 0.55: fallback model or mark for manual review

## 7. Data Model Changes
Extend RegionData with:
- normalized_text
- is_sfx
- bubble_id
- reading_order
- translation_candidates
- quality_score
- max_chars

Add quality_trace to TaskContext for stage scores and decisions.

## 8. Configuration
Add YAML config files:
- config/quality.yml: thresholds, retry policy, model fallback.
- config/glossary.yml: terminology mapping.
- config/characters.yml: character speech style and honorifics.
- config/style.yml: bubble capacity and typography limits.

## 9. Testing Plan
Minimum tests to lock quality behavior:
1) OCR post-process rules (known error cases).
2) Glossary/character consistency (deterministic input/output).
3) Layout constraints (max_chars / overflow handling).

## 10. Rollout Plan (Incremental)
Phase 1: Add configs + inject glossary into prompt; emit QualityReport JSON.
Phase 2: Enable QualityGate and retries for low scores.
Phase 3: Add LayoutEstimator + enforce length constraints in renderer.

## 11. Risks & Mitigations
- Increased cost from retries -> limit to low-confidence bubbles.
- Over-correction by OCR post-processing -> keep rules minimal and test-driven.
- Longer dev time -> incremental rollout with opt-in flags.

## 12. Open Questions (Prioritized + Proposed Defaults)
P0 (needs answer now):
- Primary model + fallback? Proposed: keep current PPIO_MODEL as primary; fallback to Gemini only if GEMINI_API_KEY is set.
- Retry budget? Proposed: 1 retry per low-score bubble; max 2 retries per image.
- Default target language? Proposed: zh-CN (matches current .env.example).

P1 (can be decided later):
- Glossary/character file format? Proposed: YAML for readability.
- Strictness of bubble-fit vs naturalness? Proposed: allow 10-15% overflow before retrying.
