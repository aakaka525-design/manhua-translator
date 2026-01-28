# Reference Font Size Anchoring Design

Date: 2026-01-28
Project: manhua
Scope: Make rendered font size track original text size while keeping bubble fit

## 1. Goal
Reduce font size mismatch between source and translated text by anchoring font size to an estimated original size, with a tight range and safe fallbacks.

## 2. Problem Summary
Current rendering uses `fit_text_to_box()` with fixed min/max (16-32). This ignores original text size and causes many regions to clamp to extremes, producing visible size mismatch.

## 3. Decisions
- **Anchor range (chosen):** 0.85x to 1.15x of the estimated original font size.
- **Primary reference:** `StyleEstimator.estimate_font_size()` on the original image and box.
- **Override:** If `RegionData.font_style_params.font_size` is set explicitly (non-default), prefer it as the reference size.
- **Fallback:** If reference size is unavailable or invalid, use the current fixed range (16-32).
- **Relaxation:** If translated text cannot fit within the anchored range, allow controlled downscaling and record that it was relaxed.

## 4. Proposed Flow
Render stage only:
1. For each region, compute `ref_size` from original image/box (or override).
2. Compute `min_size = round(ref_size * 0.85)` and `max_size = round(ref_size * 1.15)`.
3. Run `fit_text_to_box(text, box, min_size, max_size)`.
4. If no fit inside the range, reduce size below `min_size` until it fits (bounded by a global minimum), and mark `font_size_relaxed=true`.
5. If reference size is missing or invalid, fall back to fixed range (16-32).

## 5. Algorithm Details
- Add a new helper in `TextRenderer` (e.g., `fit_text_to_box_with_reference`).
- Validate `ref_size` (positive int, sane range).
- Clamp computed min/max against global safety bounds.
- Return `{font_size_used, lines, font_size_ref, font_size_relaxed}` for telemetry.

## 6. Telemetry / Data
Add (to region-level report or region metadata):
- `font_size_ref`: reference size used for anchoring
- `font_size_used`: final rendered font size
- `font_size_relaxed`: boolean indicating fallback below anchored range
- `font_size_source`: one of `estimate`, `override`, `fallback`

## 7. Configuration
Add `config/style.yml` (or extend existing style config) with:
- `font_size_ref_range: [0.85, 1.15]`
- `font_size_fallback: [16, 32]`
- `font_size_relax_min: 12` (global safety minimum)

## 8. Tests (Minimum)
1. **Anchored fit:** Given a ref size and a short text, ensure `font_size_used` is within the anchored range.
2. **Fallback:** Missing original image or invalid ref size uses fallback range.
3. **Relaxation:** Very long text triggers `font_size_relaxed=true` and fits within the box.
4. **Override:** Explicit `font_style_params.font_size` is honored as reference.

## 9. Non-Goals
- Changing OCR or translation logic.
- Full style transfer beyond font size (color/stroke remain as-is).
- Page-level font normalization.
