# QualityGate Phase 3 Design (Auto Retry + Fallback)

Date: 2026-01-27
Project: manhua
Scope: Automatic retry and fallback for low-quality translation regions

## 1. Goal
Enable QualityGate to automatically retry low-quality regions and optionally use a high-quality fallback model (Gemini) while keeping retries bounded and localized.

## 2. Decisions
- Retry granularity: per region only
- Retry thresholds: 0.75 accept / 0.55 retry
- Retry budgets: 1 retry per low-score region, max 2 retries per image
- Fallback model: Gemini (high quality) when GEMINI_API_KEY is present
- Retry prompt: configurable via config/quality.yml template
- SFX policy: SFX regions skip retries

## 3. Architecture (Chosen)
Create a standalone QualityGate module (core/quality_gate.py) that evaluates regions and performs retry/fallback. Pipeline calls QualityGate after translation and before inpainting.

## 4. Data Flow
Translation -> QualityGate -> Inpainting
- QualityGate evaluates each region, retries low-score ones, and updates region fields
- QualityReport records retries, model_used, and updated scores

## 5. Retry Logic
1) Evaluate region quality using Phase 2 scoring.
2) If score < 0.55 and retry budget allows:
   - Build retry prompt using template from config/quality.yml
   - Retry with same model once
3) If still low and GEMINI_API_KEY exists:
   - Retry with Gemini (fallback)
4) Update region with final target_text, quality_score, signals, recommendations

## 6. Fallback Translator Instantiation
Preferred: TranslatorModule exposes create_translator(model_name) factory.
Alternative: QualityGate manages its own translator map (less ideal).

## 7. Prompt Template
Config-driven template (config/quality.yml):
```
retry_prompt_template: |
  请将以下文本翻译得更简洁（不超过{max_chars}字）：
  {source_text}
  保留专有名词：{glossary_terms}
  仅输出翻译结果。
```
Placeholders: {max_chars}, {source_text}, {glossary_terms}

## 8. Error Handling
- If fallback unavailable, log and continue without blocking pipeline
- Retry failures are captured in QualityReport

## 9. Tests (Minimum)
1) Low-score region triggers retry with same model
2) Retry still low -> fallback invoked when GEMINI_API_KEY set
3) Retry budget per image enforced
4) Prompt template substitution correct
5) Fallback unavailable does not crash
6) SFX regions skip retries

## 10. Non-Goals
- Global re-translation of full image
- Model selection optimization
- UI changes
