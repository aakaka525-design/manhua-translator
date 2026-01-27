# Pipeline Quality-First Design (Manhua)

Date: 2026-01-27
Project: manhua
Focus: OCR → Translation → Inpainting → Rendering quality improvements

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
Keep the 4-stage pipeline but add quality-focused sub-modules:

- OCR
  - OCRPostProcessor: normalize text, fix common OCR errors, language-aware corrections.
- Translation
  - BubbleGrouper: group regions by bubble and reading order.
  - ContextBuilder: build bounded context per bubble/page.
  - TranslationOrchestrator: glossary + character lexicon + length constraints.
  - QualityGate: score output and trigger retries/fallback models.
- Inpainting
  - unchanged; receives regions marked for render/skip.
- Rendering
  - LayoutEstimator: compute max chars and orientation for better fit.
  - Renderer: respect max_chars and typography rules.

## 5. Data Model Changes
Extend `RegionData` with:
- normalized_text
- is_sfx
- bubble_id
- reading_order
- translation_candidates
- quality_score
- max_chars

Add `quality_trace` to `TaskContext` for stage scores and decisions.

## 6. Quality Gate (Scoring + Retry)
Score output using:
- OCR confidence + normalized text heuristics
- Length ratio vs bubble capacity
- Punctuation/intonation checks
- Glossary/character dictionary coverage

If score < threshold:
- Retry with alternative prompt (“more concise / more natural”).
- Optionally switch to higher-quality model.
- Only retry low-confidence bubbles to control cost.

## 7. Configuration
Add YAML config files:
- config/quality.yml: thresholds, retry policy, model fallback.
- config/glossary.yml: terminology mapping.
- config/characters.yml: character speech style and honorifics.
- config/style.yml: bubble capacity and typography limits.

## 8. Testing Plan
Minimum tests to lock quality behavior:
1) OCR post-process rules (known error cases).
2) Glossary/character consistency (deterministic input/output).
3) Layout constraints (max_chars / overflow handling).

## 9. Rollout Plan (Incremental)
Phase 1: Add configs + inject glossary into prompt; emit QualityReport JSON.
Phase 2: Enable QualityGate and retries for low scores.
Phase 3: Add LayoutEstimator + enforce length constraints in renderer.

## 10. Risks & Mitigations
- Increased cost from retries → limit to low-confidence bubbles.
- Over-correction by OCR post-processing → keep rules minimal & test-driven.
- Longer dev time → incremental rollout with opt-in flags.

## 11. Open Questions
- Preferred models and max retry budget?
- Target languages (zh-CN vs zh-TW) default?
- How strict should bubble-fit be vs translation naturalness?
