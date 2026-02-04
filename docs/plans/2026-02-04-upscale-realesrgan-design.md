# Design: Real-ESRGAN Post-Render Upscale

Date: 2026-02-04
Status: Draft (validated via brainstorming)

## Summary
Add an optional post-render super-resolution step using the **Real-ESRGAN ncnn-vulkan binary** to improve final manga image clarity. The upscale runs **after rendering**, **overwrites the final translated image**, and is **disabled by default**. The binary is downloaded during dependency setup (local) and during Docker build (cloud). Missing binary or failures **error out with a clear prompt** (no silent fallback).

## Goals
- Improve final image clarity without touching OCR/translation logic.
- Keep deployment simple on macOS and Linux via a fixed binary release.
- Provide a reproducible, opt-in pipeline with controlled env vars.
- Provide an evaluation script to compare OCR confidence before/after.

## Non-Goals
- No changes to OCR detection logic or translation behavior.
- No Windows support in v1.
- No GPU selection logic beyond logging a CPU fallback warning.

## Key Decisions (locked)
- Execution stage: **post-render** (after `Renderer`).
- Output behavior: **overwrite** the final `*_translated.png` (safe temp file + move).
- Default enable: **off** (`UPSCALE_ENABLE=1` to enable).
- Default scale: **2x**.
- Default model: **realesrgan-x4plus-anime**.
- Binary management: **fixed version** downloaded into `tools/bin` (local) and `/opt/tools` (Docker).
- Failure handling: **raise with prompt** (no silent fallback).
- Evaluation: **standalone script** with OCR confidence gain; JSON default, CSV optional.

## Architecture & Flow
- Add `core/modules/upscaler.py` implementing `UpscaleModule.process(context)`.
- Pipeline: `Renderer` -> `UpscaleModule` (if enabled) -> output.
- `UpscaleModule` calls the ncnn binary via `subprocess`, uses a temp output file in the same directory, then atomically replaces the final file with `shutil.move`.
- Log duration, model, scale, and CPU fallback hint; do **not** log image contents.

## Configuration (env vars)
- `UPSCALE_ENABLE` (default `0`) — enable/disable upscale.
- `UPSCALE_BINARY_PATH` (default platform-based):
  - macOS: `tools/bin/realesrgan-ncnn-vulkan`
  - Linux: `tools/bin/realesrgan-ncnn-vulkan`
  - Docker will set `/opt/tools/realesrgan-ncnn-vulkan` explicitly.
- `UPSCALE_MODEL` (default `realesrgan-x4plus-anime`).
- `UPSCALE_SCALE` (default `2`).
- `UPSCALE_TIMEOUT` (default `120` seconds).

## Installation & Binary Management
### Local (pip)
- New `scripts/setup_local.sh`:
  - `pip install -r requirements.txt` (or `requirements-cpu.txt`),
  - download fixed binary release to `tools/bin/`,
  - `chmod +x` and verify executable.

### Docker (cloud)
- Docker build stage downloads the fixed binary release into `/opt/tools`.
- `UPSCALE_BINARY_PATH` set in Dockerfile or docker-compose env.

## Error Handling & Safety
- If binary is missing or not executable: **raise error** with prompt to run `scripts/setup_local.sh` or rebuild Docker image.
- If subprocess times out: raise with timeout message.
- If subprocess fails: include stderr tail in error.
- Use temp output file + `shutil.move` to avoid corrupted final images.

## CPU Fallback Warning
- If stderr indicates CPU fallback (or runtime exceeds a threshold), log a warning: “Vulkan unavailable, CPU fallback may be slow.”

## Evaluation Script
- `scripts/upscale_eval.py`:
  - Input: single image or directory.
  - Process: run OCR on original and upscaled outputs.
  - Output: JSON report by default, `--format csv` optional.
  - Metrics: avg/median confidence and `gain_ratio = (new-old)/old`.
  - Flags: `--min-gain` to mark suggested keep/skip for human review.
  - Output path: `output/upscale_eval/<timestamp>/report.json`.

## Testing
- Unit tests:
  - `tests/test_upscaler_module.py` using subprocess mocks.
  - Validate temp file replacement and timeout handling.
- Integration test:
  - Run on a sample image in macOS venv; confirm output exists and size increased.
- Eval script test:
  - Mock OCR outputs; validate confidence gain calculation and JSON format.

## Open Items
- Confirm Dockerfile location and best place to insert binary download steps.
- Decide whether to record CPU fallback using stderr parsing or runtime threshold only.
