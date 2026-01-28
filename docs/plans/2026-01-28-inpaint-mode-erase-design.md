# Inpaint Mode "Erase" Integration Design

Date: 2026-01-28
Project: manhua
Scope: Make `inpaint_mode="erase"` take effect in inpainting while preserving SFX

## 1. Goal
Ensure watermark regions (and any region flagged with `inpaint_mode="erase"`) are inpainted even when `target_text` is empty, while SFX regions are not inpainted and remain on the original image.

## 2. Decisions
- **SFX policy:** Do not inpaint SFX regions; keep the original art/text.
- **Erase policy:** Any region with `inpaint_mode="erase"` must be inpainted regardless of `target_text`.
- **Config:** No new config file; hardcode the rules for now.

## 3. Current Data Flow
OCR -> Translation -> Inpainting -> Rendering

- WatermarkDetector sets `region.is_watermark=True` and `region.inpaint_mode="erase"`.
- Translator skips watermark regions and leaves `target_text` empty.
- Inpainter currently only inpaints regions with non-empty `target_text`.

## 4. Proposed Logic (Chosen)
Modify `core/modules/inpainter.py` to compute `regions_to_inpaint` with these rules:

- **Always inpaint** when `inpaint_mode == "erase"`.
- **Inpaint for replacement** when `target_text` is non-empty **and** region is not SFX.
- **Skip inpainting** otherwise (including SFX regions and empty text with `inpaint_mode != "erase"`).

Renderer behavior remains unchanged (it already skips empty text, `[SFX: ...]`, and `[INPAINT_ONLY]`).

## 5. Error Handling
- Missing fields are treated with defaults:
  - `inpaint_mode` defaults to `"replace"`
  - `is_sfx` defaults to `False`
- The filtering step should use `getattr(..., default)` to avoid crashes on older data.

## 6. Tests (Minimum)
1. **Erase watermark:** `inpaint_mode="erase"` + empty `target_text` -> included in inpaint list.
2. **SFX skip:** `is_sfx=True` -> excluded from inpaint list.
3. **Normal replace:** `target_text` non-empty and not SFX -> included.
4. **Empty replace:** `target_text` empty and `inpaint_mode="replace"` -> excluded.

## 7. Non-Goals
- Add new configuration files.
- Change renderer behavior or SFX detection.
- Introduce model-based watermark detection.
