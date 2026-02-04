# Upscale Stripe Segmentation Design

**Goal:** Speed up PyTorch Real-ESRGAN on very tall images by slicing into horizontal stripes with overlap, then stitching outputs seamlessly.

**Motivation:** Current MPS path is slow on long pages (e.g., 720×15503). Splitting reduces per-inference size and stabilizes memory use.

## Non-Goals
- ROI/text-region-only upscale (not in this change).
- Streaming-on-disk merge (optional future).
- Model change or quality optimization.

## Configuration (env)
- `UPSCALE_STRIPE_ENABLE` (default `0`): enable stripe mode.
- `UPSCALE_STRIPE_THRESHOLD` (default `4000`): only split when `H > threshold`.
- `UPSCALE_STRIPE_HEIGHT` (default `2000`): stripe height.
- `UPSCALE_STRIPE_OVERLAP` (default `64`): overlap height in pixels (input space).

## Core Functions (testable)
```python
def compute_stripes(height: int, threshold: int, stripe_height: int, overlap: int) -> list[tuple[int, int]]:
    """Return [(start, end), ...] ranges in input space."""

def crop_and_merge(stripes: list[np.ndarray], overlap_px: int, scale: int) -> np.ndarray:
    """Trim overlaps from each output stripe and concatenate along height."""
```

### `compute_stripes`
- If `height <= threshold`, return a single stripe `(0, height)`.
- Require `stripe_height > overlap`. If not, raise `ValueError`.
- Build stripes with sliding window:
  - `start=0`, `end=min(start+stripe_height, height)`.
  - If remaining tail `< overlap`, merge into the last stripe by setting `end=height`.
  - Next `start = end - overlap`.
- Ensures the last stripe is not smaller than overlap.

### `crop_and_merge`
- `overlap_px = int(overlap * scale)` computed by caller.
- For N stripes:
  - first: keep `[0 : -overlap_px]`
  - middle: keep `[overlap_px : -overlap_px]`
  - last: keep `[overlap_px : end]`
- Concatenate along height to rebuild full output.
- If `overlap_px == 0`, keep full stripes.

## PyTorch Flow
1. Read image via `cv2.imread`.
2. If `UPSCALE_STRIPE_ENABLE=1` and `H > threshold`:
   - Compute stripes.
   - Log stripe summary.
   - For each stripe, run `RealESRGANer.enhance` and log per-stripe timing.
   - Merge via `crop_and_merge`.
3. Else, run single `enhance`.
4. Write temp output and move into place (existing behavior).

## Logging
```python
logger.info("stripe: segments=%d h=%d threshold=%d overlap=%d", n, H, threshold, overlap)
logger.debug("stripe[%d]: input_h=%d output_h=%d ms=%.0f", i, in_h, out_h, elapsed)
logger.error("stripe[%d] failed: input_size=%sx%s error=%s", i, w, h, e)
```

## Error Handling
- If any stripe fails, raise `RuntimeError` and preserve original output.
- Validate stripe config early and fail fast with clear message.

## Tests
- `compute_stripes` returns single stripe when `H <= threshold`.
- Tail smaller than overlap merges into previous stripe.
- `crop_and_merge` produces correct total height for scale.
- `H == threshold` does **not** trigger stripe mode.

## Acceptance
- Stripe mode reduces per-inference size and finishes on tall images.
- Output height equals `H * scale` and no visible seams.
- Logs show stripe summary and per-stripe timings.
