# Output Format (WebP) Design

## Goal
Default all pipeline outputs to WebP to reduce storage, while allowing a global opt‑out to PNG for debugging/compatibility.

## Scope
- Final translated images
- Inpaint masks and inpainted intermediates
- Debug artifacts and OCR overlays
- Upscaler outputs (pytorch and ncnn)
- Output file discovery in API routes

## Non‑Goals
- Change input image formats
- Alter OCR/translation logic
- Add additional formats beyond WebP/PNG

## Design Summary
Introduce a single image save utility with a format switch controlled by env vars:

- `OUTPUT_FORMAT=webp|png` (default: `webp`)
- `WEBP_QUALITY_FINAL=90` (lossy, final output)
- `WEBP_LOSSLESS_INTERMEDIATE=1` (lossless, intermediates/debug)

All image writers call:

```python
save_image(image, path, purpose="final"|"intermediate") -> str
```

The function:
- Normalizes the output suffix based on `OUTPUT_FORMAT`
- Applies WebP quality/lossless settings based on `purpose`
- Returns the actual saved path (with updated suffix)

## File Discovery Compatibility
When checking translated outputs in `manga.py` and `translate.py`, use glob‑based discovery by stem and prefer WebP if available:

```python
translated_files = list(output_dir.glob(f"{stem}.*"))
```

## Error Handling
- If WebP encoding fails, raise and surface via existing pipeline error paths.
- If `OUTPUT_FORMAT` is unsupported, raise `ValueError` early with clear message.

## Testing
- Unit tests for `save_image` (suffix rewrite, purpose settings).
- Regression test that renderer produces `.webp` when OUTPUT_FORMAT=webp.
- API route discovery test: choose `.webp` over `.png` when both exist.

