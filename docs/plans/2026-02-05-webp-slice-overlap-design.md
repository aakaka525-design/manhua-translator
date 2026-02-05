# WebP Slice Overlap Configuration Design

## Summary
Introduce a configurable overlap for WebP slicing via environment variable `WEBP_SLICE_OVERLAP` (default `10`). The overlap is written into `*_slices.json` and used by frontends for seam-free rendering. This keeps the default behavior aligned with the tested best value while preserving runtime tuning flexibility.

## Goals
- Default overlap = 10px for smoother visual seams.
- Allow runtime adjustment without code changes.
- Keep JSON index self-descriptive for frontends.

## Non-Goals
- Changing slice height or adding additional slicing parameters (can be added later if needed).
- Modifying existing frontends beyond reading the JSON overlap value.

## Design
### Configuration
- New env var: `WEBP_SLICE_OVERLAP`
  - Default: `10`
  - Scope: WebP slicing only (final outputs when height > 16383).

### Behavior
- `core/image_io._save_webp_slices` reads `WEBP_SLICE_OVERLAP` and passes it to `compute_webp_slices`.
- `*_slices.json` uses this overlap in the `overlap` field, so renderers can cut exactly the same overlap when stacking slices.

### Backward Compatibility
- If older JSON files don’t include `overlap`, renderers should continue to use their default fallback (existing behavior).
- If the env var is unset, behavior defaults to `10`.

## Documentation
- Update `README.md` to mention `WEBP_SLICE_OVERLAP`.
- Update `.env.example` to include `WEBP_SLICE_OVERLAP=10`.

## Testing
- Update/add unit test to validate that the JSON `overlap` equals the configured env value.
- Run focused tests for `image_io` and slice logic.
