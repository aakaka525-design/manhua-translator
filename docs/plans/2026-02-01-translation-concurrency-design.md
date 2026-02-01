# Translation Batch Concurrency Design

## Goal
Reduce end-to-end translation latency by running multiple smaller batch calls in parallel, while keeping the existing public API unchanged for callers.

## Scope
- Implement concurrency inside `core/ai_translator.py::AITranslator.translate_batch`.
- Keep existing parsing, retry, and output behavior stable.
- Add minimal configuration via environment variables.

## Proposed Approach
1. **Chunking**: Split `valid_pairs` into slices of size `AI_TRANSLATE_BATCH_CHUNK_SIZE` (default: 8). If the number of slices is 1, keep the current single-call path.
2. **Concurrency Control**: Use an `asyncio.Semaphore` with `AI_TRANSLATE_BATCH_CONCURRENCY` (default: 8) to bound concurrent `_call_api` invocations.
3. **Per-slice Prompt**: For each slice, build `numbered_texts` and `prompt` exactly as today (including CTX). Reuse the existing output parsing logic (`numbered` / `json`) to produce slice results.
4. **Merge**: Gather all slice results and reconstruct `full_results` in the original order.

## Error Handling & Retries
- Keep the existing `max_retries` logic per slice.
- A failure in one slice only affects that slice; other slices complete normally.
- Optional: add a small retry jitter for rate-limit errors (429/503) to reduce thundering herds.

## Logging & Metrics
- Keep existing `batch:` logs.
- Add slice-level context to logs (slice index/total, count, length) when concurrency is enabled.
- Preserve existing metrics output to avoid breaking dashboards.

## Testing / Validation
- Manual validation with:
  - Small batch (<= chunk size): ensure behavior matches current output.
  - Larger batch (> chunk size): verify ordering and count match input.
  - `output_format="json"`: verify JSON line parsing works per slice.

## Risks
- Higher request rate may trigger provider rate limits; concurrency is bounded and configurable.
- Larger total overhead from multiple prompts; offset by reduced wall-clock latency in high-latency providers.

## Non-Goals
- Changing the prompt format or translation quality heuristics.
- Modifying any caller in `core/modules/translator.py`.
