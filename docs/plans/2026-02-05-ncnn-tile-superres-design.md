# NCNN Tile Super-Resolution Design

## Summary
Enable NCNN tiling for full-image super-resolution and then slice the upscaled output into WebP slices. This avoids seam artifacts from per-slice inference while keeping memory bounded using `-t <tile>` on the NCNN binary.

## Goals
- Use NCNN tile mode for full-image upscale to avoid seam artifacts.
- Reuse existing `UPSCALE_TILE` configuration (no new env var).
- Keep current slice output format and JSON index.

## Non-Goals
- Changing slice height or overlap behavior (handled separately).
- Modifying front-end rendering logic.
- Adding new NCNN-specific configuration knobs.

## Design
### Configuration
- Reuse `UPSCALE_TILE` for NCNN:
  - `0` = disabled (no `-t` argument)
  - `>0` = pass `-t <tile>` to `realesrgan-ncnn-vulkan`

### Behavior
- In `core/modules/upscaler.py` `_run_ncnn`, read `UPSCALE_TILE`.
- If `tile > 0`, add `-t <tile>` to NCNN command.
- Log tile value in the “Upscaler start (ncnn)” message.
- Record `tile` in `last_metrics` for later inspection.

### Data Flow
1. Rendered output is upscaled by NCNN with optional tiling.
2. Output image is saved; if WebP exceeds size limits, slice into `*_slices/` + `*_slices.json`.
3. Frontend renders slices as usual (no seam artifacts from inference).

## Testing
- Add a unit test to verify `-t` is included when `UPSCALE_TILE>0` (mock `subprocess.run`).
- Verify `tile` is written into `last_metrics`.

## Documentation
- Update `README.md` to state `UPSCALE_TILE` applies to both PyTorch and NCNN.
