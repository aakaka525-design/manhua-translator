# Watermark Filtering Design (Rule-First)

Date: 2026-01-28
Project: manhua
Scope: Detect watermarks and erase without translation

## 1. Goal
Prevent watermark text from being translated and rendered. Watermark regions should be erased (background repair) and excluded from translation.

## 2. Strategy (Rule-First)
Primary rules:
- Keyword/URL match (case-insensitive) ⇒ watermark
- Position near edges/corners/bottom-center
- Cross-page repetition at similar positions

Fallback: If rules are insufficient, later add a lightweight classifier.

## 3. Data Flow
OCR → OCRPostProcessor → WatermarkDetector → Translation (skip watermark) → Inpainting (erase) → Rendering

## 4. Data Model Changes
Extend RegionData:
- is_watermark: bool
- inpaint_mode: "erase" | "replace" (watermark = erase)

## 5. Rules
### 5.1 Hard rules (direct watermark)
- Contains URL or domain-like strings: http/https, .com, .net, .org
- Contains site/copyright keywords (case-insensitive)

### 5.2 Soft rules (score-based)
- Position within outer 10% margins or bottom-center band
- Short length (≤20 chars)
- Repeats across pages in similar location

## 6. Default Keyword List (lowercase)
- Domains/site fragments: mangaforfree, toongod, manga, manhua, comic, scan, raw, sub
- Copyright: copyright, all rights reserved, ©

## 7. Inpainting Policy
- Watermark: inpaint_mode = erase (background repair, no text)
- Normal text: inpaint_mode = replace

## 8. Testing Plan
1) URL/keyword hit ⇒ watermark
2) Case-insensitive keyword match
3) Position+short text+repeat ⇒ watermark
4) Dialogue text not flagged
5) Watermark sets inpaint_mode = erase
6) SFX not misclassified
7) Cross-page repetition detection (simulate same text at similar coords on multiple pages)

## 9. Non-Goals
- Perfect detection in all cases
- Training a watermark classifier (later)
