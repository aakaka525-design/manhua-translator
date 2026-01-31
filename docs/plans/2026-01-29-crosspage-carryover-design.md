# Crosspage CarryOver Translation Design

Date: 2026-01-29
Project: manhua
Focus: Cross-page bubble continuity with two-part translation output and carryover state

## 1. Background
Long-strip comics often split a single dialogue bubble across page boundaries. The current pipeline can append crosspage text for translation, but it does not expand the inpaint box and does not render a continuation on the next page. This causes residual original text and missing translations at page joins.

## 2. Goals
- Preserve semantic continuity across split bubbles.
- Ensure both page halves are fully erased and correctly rendered.
- Keep MVP behavior sequential and recoverable.
- Add minimal, testable infrastructure (carryover store + JSON output parsing).

## 3. Non-Goals
- Global chapter pre-scan for default mode (can be optional high-quality mode).
- Major changes to OCR engine or renderer layout algorithm.
- Large-scale performance optimization.

## 4. Proposed Flow (Overview)
- Keep two independent Regions (current bottom / next top) with their own box_2d for erase/render.
- Translate once per crosspage pair using model output in JSON: {"top": "...", "bottom": "..."}.
- Write `top` to current page region; store `bottom` to carryover for next page.
- When processing the next page, if a matching pair_id exists, fill target_text from carryover and skip translation.

## 5. Crosspage State CarryOver
### 5.1 Store
Add a lightweight `CrosspageCarryOverStore` (chapter/session scope) that stores:
- pair_id
- bottom_text
- from_page / to_page
- created_at
- status (pending / consumed)

### 5.2 Persistence
Persist as JSONL: `output/quality_reports/_carryover.jsonl` for resumability. If process crashes at page N, page N+1 can still consume stored bottom_text.

### 5.3 Ordering (MVP)
Process pages sequentially. The pipeline already tends to use ordered await in batch_translate; the MVP should enforce or document that sequential order is required.

## 6. Pairing Strategy
### 6.1 Pair ID
Pair ID should be stable across N and N+1:
- Use a hash of (edge_box_2d rounded coords + normalized_text) or
- Use OCR box position fingerprint with tolerance + text fingerprint.

### 6.2 Matching
- Page N: match current bottom with next page top using existing next_top sampling.
- Page N+1: recompute pair_id and lookup carryover.

## 7. Translation Output Format (JSON)
### 7.1 Prompt
Force model to output **only** JSON:
```json
{"top":"...","bottom":"..."}
```

### 7.2 Parser & Fallback
- Strict JSON parse first.
- If parse fails, fallback to regex extraction or proportional split.
- If still failing, log error and keep only top to avoid empty output.

## 8. Data Model Additions
- `crosspage_pair_id`: str
- `crosspage_role`: enum (current_bottom / next_top)
- `crosspage_pending`: bool (optional)

## 9. Implementation Steps (High Level)
1) OCR: compute pair_id and crosspage_role for matched pairs.
2) Translator: build combined_text for crosspage pair, prompt for JSON output, parse into top/bottom.
3) Store: persist bottom to carryover for next page.
4) Next page: if carryover found for pair_id, fill target_text and skip translation.

## 10. Testing
- Unit: carryover store read/write/persist/consume.
- Unit: JSON parse success + fallback behavior.
- Integration: simulated crosspage pair across two pages with carryover.
- **Mock OCR end-to-end**: produce "He" (page N) + "llo" (page N+1), ensure output reads as "Hello" and both pages render correctly.

## 11. Risks & Mitigations
- Model JSON format drift → fallback parser + logging.
- Pair ID mismatch → looser matching tolerance, retry with secondary key.
- Non-sequential batch → warn or force sequential in MVP.

## 12. Optional High-Quality Mode
A `mode="high_quality"` could pre-scan entire chapter for pairing before translation. Default remains sequential carryover.
