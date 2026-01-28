# Watermark Rules Config Design

Date: 2026-01-28
Project: manhua
Scope: Configurable watermark detection rules

## 1. Goal
Make watermark detection rules configurable via `config/watermark.yml` while keeping safe defaults and low false positives.

## 2. Decisions
- Config file: `config/watermark.yml`
- Default signals: keyword/URL, edge+short text (weak), cross-page repetition
- Keyword list: built-in defaults + config append (mode=append by default)
- Thresholds: edge_ratio=0.10, pos_tolerance_px=20, max_text_length=20
- Cross-page repetition scope: in-process cache only (same run)

## 3. Architecture & Data Flow
OCR -> OCRPostProcessor -> WatermarkDetector -> Translation -> Inpainting -> Rendering

`WatermarkDetector` loads config once (on init) and applies rules:
1) Keyword/URL match (strong)
2) Edge + short text (weak)
3) Cross-page repeat at near position (strong)

On match: `region.is_watermark=True` and `region.inpaint_mode="erase"`.

## 4. Config Structure (YAML)
```yaml
keywords:
  mode: append   # append | override
  list:
    - mangaforfree
    - toongod
    - scanlation
    - raw
    - http
    - https

position:
  edge_ratio: 0.10
  max_text_length: 20

repeat:
  pos_tolerance_px: 20
```

## 5. Error Handling
- Missing or invalid config: warn and use defaults
- Unknown fields are ignored
- Text is normalized to lowercase before keyword matching

## 6. Tests (Minimum)
1) Keyword match from config (case-insensitive)
2) Mode append vs override
3) Edge + short text requires both signals
4) Cross-page repeat within tolerance
5) Config missing/invalid falls back to defaults

## 7. Non-Goals
- Persisting repeat cache across runs
- ML-based watermark detection
- UI changes
