# Font Size Estimator V2 (Design)

Date: 2026-01-28
Project: manhua
Goal: Make translated text **closer to original size** (slightly larger overall) while preserving bubble fit and good line breaks.

## 1. Background
Current font sizing uses a coarse area-based estimate in `StyleEstimator.estimate_font_size()` plus a reference range. This can produce sizes that are too small or too large, and in long-text cases the final result may shrink unnecessarily.

## 2. Goals
- Make font size **slightly larger** by default (user preference).
- Improve size estimation with a **line-count-aware** model.
- Keep layout stable: no overflow or single-line collapse for long text.
- Make adjustments configurable via `config/style.yml`.

## 3. Non-Goals
- Full typography redesign.
- Changing translation content.
- Replacing OCR or renderer architecture.

## 4. Proposed Changes (High-Level)
1) Replace the current area-based estimate with a **line-count-aware** estimate.
2) Add a configurable **font size bias** to slightly increase estimated size.
3) When multi-line text nearly overflows, try **compact line spacing** before shrinking the font size further.

## 5. Algorithm (V2)
Given `box (w, h)` and `text_length`:
- `available_width = w * (1 - 2 * padding_ratio)`
- `available_height = h * (1 - 2 * padding_ratio)`
- Estimate number of lines:
  - `lines = ceil(sqrt(text_length * available_height / (available_width * line_spacing)))`
  - Clamp `lines >= 1`
- Compute size candidates:
  - `size_by_height = available_height / (lines * line_spacing)`
  - `size_by_width = available_width / ceil(text_length / lines)`
- `size = min(size_by_height, size_by_width)`
- Apply bias: `size *= font_size_estimate_bias`
- Clamp to `[min_size, max_size]`

**Compact line spacing** (optional):
- If `total_height > available_height * line_spacing_compact_threshold`, recompute using `line_spacing_compact`.

## 6. Configuration (config/style.yml)
New keys:
- `font_size_estimate_bias: 1.10`
- `line_spacing_default: 1.2`
- `line_spacing_compact: 1.1`
- `line_spacing_compact_threshold: 0.9`

## 7. Data Flow
- `StyleEstimator.estimate_font_size()` uses V2 algorithm + bias.
- `TextRenderer.fit_text_to_box_with_reference()` optionally recomputes line spacing if near overflow.
- `RegionData` metadata (font_size_ref/used/relaxed) remains unchanged.

## 8. Testing Plan
- Unit: estimation bias increases size.
- Unit: long text in medium box results in multi-line layout.
- Unit: compact line spacing triggers before reducing font size.
- Visual: re-run sample `/data/raw/wireless-onahole/chapter-71-raw/2.jpg` and compare.

## 9. Risks
- Over-bias could overflow bubbles.
- Line-spacing compact may reduce readability if used too often.

## 10. Rollback
Set `font_size_estimate_bias = 1.0` and `line_spacing_compact = line_spacing_default`.
