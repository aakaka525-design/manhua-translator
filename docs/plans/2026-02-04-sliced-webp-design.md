# Sliced WebP Design (Oversize Page Output)

**Goal**
Generate WebP outputs for very tall pages by slicing into multiple WebP files with a JSON index, avoiding the 16383px WebP height limit while keeping output size small and reader-friendly.

**Scope**
- Triggered only when `OUTPUT_FORMAT=webp` and output height exceeds WebP limit.
- Uses slicing for final output only; OCR/translation/inpaint/upscale unchanged.
- Frontend renders slices as stacked images with overlap handling.

**Out of Scope**
- Changing existing OCR/translation/inpaint/upscale logic.
- Replacing WebP as default output format.

---

## Trigger Rules
- If `OUTPUT_FORMAT=webp` **and** `height > 16383`: slice output.
- Otherwise: keep current single-file output.

## Slice Parameters (Defaults)
- `slice_height = 16000`
- `overlap = 32`
- `stride = slice_height - overlap`

## Output Layout
- Directory: `<stem>_slices/`
- Files: `slice_000.webp`, `slice_001.webp`, ...
- Index: `<stem>_slices.json`

## Index JSON Schema
```json
{
  "version": 1,
  "original_width": 2880,
  "original_height": 62012,
  "slice_height": 16000,
  "overlap": 32,
  "slices": [
    {"file": "slice_000.webp", "y": 0, "height": 16000},
    {"file": "slice_001.webp", "y": 15968, "height": 16000},
    {"file": "slice_002.webp", "y": 31936, "height": 16000},
    {"file": "slice_003.webp", "y": 47904, "height": 14108}
  ]
}
```
- `y` is the actual start position: `i * (slice_height - overlap)`.
- `height` is the actual height for the slice (last slice may be shorter).

## Failure Handling
- If any slice write fails: fallback to **single PNG** output.
- Log fallback reason.

## Logging
- `logger.info("slice_mode: {n} slices, total_height={h}")`
- Log output directory and index file path.

---

## Frontend Rendering
Preferred (no visible seams):
```css
.manga-page img + img {
  margin-top: -32px;
  clip-path: inset(32px 0 0 0);
}
```
Fallback (no clip-path):
```html
<img src="slice_000.webp">
<img src="slice_001.webp" style="margin-top:-32px">
```

---

## Testing Strategy
**Unit tests** (slice math):
```python
@pytest.mark.parametrize("height,expected_slices", [
    (16383, 1),
    (16384, 2),
    (32000, 2),
    (62012, 4),
])
```
- Validate slice count, `y` positions, last slice height.

**File tests**
- Verify slice files exist and JSON matches computed values.

**Manual render check**
- Load slices in a minimal HTML page to confirm no seams.

---

## Configuration (Future-Proof)
- Optional envs (if needed later):
  - `SLICE_WEBP_HEIGHT=16000`
  - `SLICE_WEBP_OVERLAP=32`
  - `SLICE_WEBP_ENABLE=1`

---

## Success Criteria
- WebP output never fails due to height.
- Tall pages render seamlessly in reader.
- Non-tall pages remain unchanged.
