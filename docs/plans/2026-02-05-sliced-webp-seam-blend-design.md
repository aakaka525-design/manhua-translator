# Sliced WebP Seam Blending + Lossless Slice Option

## Summary
We see visible seams between WebP slices even when overlap is fixed. The pipeline already performs full-image upscale then slice, so the remaining seam is likely due to lossy WebP compression per-slice and front-end hard clipping. This design adds (1) a lossless-only-for-slices switch to eliminate compression mismatch, and (2) a CSS gradient blend in the reader to feather overlap areas. It keeps the existing pipeline intact and only affects sliced-output rendering.

## Goals
- Remove visible seams in sliced WebP rendering.
- Keep existing full-image upscale -> slice flow unchanged.
- Minimize changes to backend and frontend.
- Provide a controlled test path to verify lossless slicing impact.

## Non-Goals
- No change to upscale models/parameters.
- No change to slice dimensions/overlap algorithm.
- No Canvas/WebGL compositor in the reader.
- No change to unsliced (single-image) rendering.

## Key Decisions
1. Lossless only for slices via `WEBP_SLICES_LOSSLESS=1`.
2. CSS gradient blend for overlap area in the reader.
3. Compare mode retains single-image original and sliced translated layer.
4. Fallback: when slice JSON fails, try `.webp`, then fall back to original.

## Backend Changes
### New env var
- `WEBP_SLICES_LOSSLESS=1` (default `0`)
  - Only affects `_save_webp_slices`.
  - When enabled, each slice is saved as WebP lossless (`lossless=True`).
  - Full-image WebP remains unchanged (still uses `WEBP_QUALITY_FINAL`).

### Slice saving behavior
- `core/image_io.py::_save_webp_slices`
  - If lossless enabled: `crop.save(..., format="WEBP", lossless=True)`
  - Else: current `quality=WEBP_QUALITY_FINAL`

## Frontend Changes
### Detection
- If `translated_url` ends with `_slices.json`, treat as sliced.

### URL construction
- `baseDir = translated_url.replace("_slices.json", "_slices/")`
- `sliceUrl = baseDir + slice.file`

### Rendering structure
- `CompareSlider.vue` handles both single-image and sliced translated layer.
- When `compareMode=true`:
  - Original remains a single `<img>` overlay.
  - Translated layer can be a SliceContainer.
- Masking width (slider) applies to the translated container, not per-slice.

### CSS blend
For each slice after the first:
- `margin-top: -overlap_px`
- `mask-image: linear-gradient(to bottom, transparent 0px, black overlap_px, black 100%)`
- include `-webkit-mask-image` for Safari.

This produces a feathered transition in the overlap zone rather than a hard cut.

## Fallback Strategy
When slice JSON fails to load:
1. Attempt `translated_url.replace("_slices.json", ".webp")`
2. If that fails, fall back to `original_url`
3. Optionally toast/label failure (non-blocking).

## Testing Plan
### Unit tests (backend)
- `tests/test_image_io.py`:
  - Ensure `_save_webp_slices` uses `lossless=True` when `WEBP_SLICES_LOSSLESS=1`.

### Manual tests (frontend)
1. Normal sliced JSON rendering.
2. Compare mode slider with sliced translated layer.
3. Force JSON 404 -> verify fallback to `.webp`.
4. Toggle overlap and verify seam reduction.

## Rollout
- Default: `WEBP_SLICES_LOSSLESS=0` (no behavior change).
- Enable only for validation runs and seam investigation.

## Open Questions
- None at this time.
