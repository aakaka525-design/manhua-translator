# OCR Consistency Evaluation (Fixed Boxes) Design

**Goal:** Evaluate upscaling quality by comparing recognition results on the same detected boxes (no re-detect), avoiding bias from OCR resizing and box count changes.

## Rationale
- OCR confidence is unstable when images are resized or detection counts change.
- Fixed boxes provide a stable comparison: “same place, same text.”

## Flow
1. **Detect on original image**  
   Use existing OCR detect on the original image to produce `regions` (boxes + text).
2. **Map boxes to upscaled image**  
   - Compute `scale_x = up_w / orig_w`, `scale_y = up_h / orig_h`.
   - For each box: apply scale, round, and clamp to image bounds.
   - Filter tiny boxes (e.g., width/height < 8 px).
3. **Recognize only**  
   Use OCR engine `recognize(image_path, regions)` on original and upscaled images separately.
4. **Normalize and compare**  
   - Normalize text: strip, collapse spaces, lowercase (for Latin).
   - Similarity = `1 - levenshtein / max(len(a), len(b), 1)`.
   - Threshold default: **0.85**.
5. **Report**  
   - Average / median similarity
   - % above threshold
   - Worst N examples (orig text, upscaled text, similarity, box coords)

## Suggested Defaults
- Similarity threshold: **0.85** (balanced sensitivity)
- Min box size: 8×8
- Output format: JSON (CSV optional)

## Artifacts
- Output report: `output/upscale_eval/<ts>/consistency.json`

