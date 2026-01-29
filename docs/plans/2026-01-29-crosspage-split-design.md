# Cross-Page Bubble Split Design

Date: 2026-01-29
Project: manhua
Scope: Cross-page bubble translation split with semantic continuity

## 1. Background
Long scroll comics can split a single dialogue bubble across two consecutive images (bottom of page N, top of page N+1). Current pipeline translates each page independently, so semantics become disjoint and residual text remains.

## 2. Goals
- Render translated text on both pages when a bubble spans pages.
- Split the translation at a natural punctuation boundary when possible.
- Keep existing OCR/translation/rendering flow for non-crosspage bubbles.
- Keep alignment centered within each bubble.

## 3. Non‑Goals
- Full chapter pre-scan or high-cost global optimization.
- Watermark detection improvements (explicitly disabled by user).
- Model-level translation quality improvements.

## 4. Approach
Introduce a cross-page split path executed only in a new sequential batch mode. The pipeline processes pages in order and pairs bottom-edge bubbles with next-page top-edge bubbles. After translation, a splitter divides the result into top/bottom segments using punctuation-first logic.

### 4.1 Crosspage Pairing Heuristic
- Identify candidate groups near **bottom** edge on page N and **top** edge on page N+1.
- Pair by approximate x-center overlap and width similarity (quantized buckets).
- If multiple candidates exist, choose smallest x-center distance.

### 4.2 Split Strategy (User Choice)
- **Primary:** split on punctuation nearest to the midpoint (，。！？…；)
- **Fallback:** length-based 45/55% split
- Always keep punctuation with the **top** segment.

### 4.3 Rendering Behavior
- Top segment renders in page N bubble (centered).
- Bottom segment renders in page N+1 bubble (centered).
- Non-paired bubbles use current rendering behavior.

## 5. Data/State
- Add optional fields to `RegionData`:
  - `crosspage_pair_id: Optional[str]`
  - `crosspage_role: Optional[str]` (`top|bottom`)
- A `CrossPageStore` holds pending bottom-edge groups until next page is processed in the same batch.

## 6. Pipeline Changes
Add a **sequential batch mode** for cross-page flow:
1) OCR for page i
2) Translator + crosspage pairing/splitting with page i and i+1
3) Inpaint + Render per page after split

This mode runs only when explicitly enabled via CLI or config to avoid affecting existing concurrent batch behavior.

## 7. Testing
- Unit tests for punctuation-first splitting
- Unit tests for pairing heuristic
- End-to-end mock test: split "Hello" -> "He"/"llo" across two pages

## 8. Rollout
- Phase 1: Implement split and pairing in sequential batch mode
- Phase 2: Validate on known crosspage examples (3.jpg/4.jpg)

## 9. Risks
- False positives on edge bubbles → mitigate with x-overlap and min height thresholds
- Sequential processing is slower → only enabled when requested
