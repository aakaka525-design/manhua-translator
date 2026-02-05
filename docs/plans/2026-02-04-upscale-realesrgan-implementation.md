# Real-ESRGAN Post-Render Upscale Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional post-render Real-ESRGAN upscale step (disabled by default) with safe output replacement, fixed binary download, and an OCR-based evaluation script.

**Architecture:** Introduce a new `UpscaleModule` stage after `Renderer`, calling the `realesrgan-ncnn-vulkan` binary with env-driven settings. Provide a local setup script to download binaries and a standalone evaluation script to compare OCR confidence before/after upscaling.

**Tech Stack:** Python 3.10, subprocess, bash, Docker, Real-ESRGAN-ncnn-vulkan binary.

---

### Task 1: Add UpscaleModule + unit tests

**Files:**
- Create: `core/modules/upscaler.py`
- Modify: `core/modules/__init__.py`
- Test: `tests/test_upscaler_module.py`

**Step 1: Write the failing tests**

Create `tests/test_upscaler_module.py`:

```python
import asyncio
from pathlib import Path
import subprocess
import pytest

from core.models import TaskContext
from core.modules.upscaler import UpscaleModule


def _make_context(tmp_path: Path) -> TaskContext:
    source = tmp_path / "input.png"
    output = tmp_path / "translated.png"
    source.write_bytes(b"fake")
    output.write_bytes(b"fake")
    return TaskContext(image_path=str(source), output_path=str(output))


def test_upscaler_skips_when_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "0")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    def _boom(*args, **kwargs):
        raise AssertionError("subprocess should not run")

    monkeypatch.setattr(subprocess, "run", _boom)
    asyncio.run(module.process(ctx))


def test_upscaler_missing_binary_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(tmp_path / "missing"))

    with pytest.raises(FileNotFoundError):
        asyncio.run(module.process(ctx))


def test_upscaler_replaces_output_with_temp(monkeypatch, tmp_path):
    monkeypatch.setenv("UPSCALE_ENABLE", "1")
    monkeypatch.setenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    monkeypatch.setenv("UPSCALE_SCALE", "2")

    binary = tmp_path / "realesrgan-ncnn-vulkan"
    binary.write_text("bin")
    binary.chmod(0o755)

    ctx = _make_context(tmp_path)
    module = UpscaleModule(binary_path=str(binary))
    calls = {}

    def _fake_run(cmd, capture_output, text, check, timeout):
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_bytes(b"upscaled")
        calls["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="Vulkan")

    monkeypatch.setattr(subprocess, "run", _fake_run)

    asyncio.run(module.process(ctx))
    assert Path(ctx.output_path).read_bytes() == b"upscaled"
    assert "realesrgan-x4plus-anime" in calls["cmd"]
```

**Step 2: Run the tests (expect failure)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_module.py`

Expected: FAIL (module not found).

**Step 3: Implement UpscaleModule**

Create `core/modules/upscaler.py`:

```python
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .base import BaseModule
from ..models import TaskContext

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "realesrgan-x4plus-anime"
DEFAULT_SCALE = 2
DEFAULT_TIMEOUT = 120


class UpscaleModule(BaseModule):
    def __init__(self, binary_path: str | None = None):
        super().__init__(name="Upscaler")
        self.binary_path = Path(binary_path) if binary_path else None
        self.last_metrics: dict | None = None

    def _enabled(self) -> bool:
        return os.getenv("UPSCALE_ENABLE", "0") == "1"

    def _resolve_binary(self) -> Path:
        if self.binary_path:
            return self.binary_path
        env_path = os.getenv("UPSCALE_BINARY_PATH")
        if env_path:
            return Path(env_path)
        # Default: project-local tools/bin
        if sys.platform.startswith("darwin"):
            return Path("tools/bin/realesrgan-ncnn-vulkan")
        if sys.platform.startswith("linux"):
            return Path("tools/bin/realesrgan-ncnn-vulkan")
        return Path("tools/bin/realesrgan-ncnn-vulkan")

    async def process(self, context: TaskContext) -> TaskContext:
        if not self._enabled():
            return context
        if not context.output_path:
            logger.warning("[%s] Upscaler skipped: no output_path", context.task_id)
            return context

        binary = self._resolve_binary()
        if not binary.exists():
            raise FileNotFoundError(
                f"Upscale binary not found: {binary}. Run scripts/setup_local.sh or rebuild Docker image."
            )
        if not os.access(binary, os.X_OK):
            raise PermissionError(f"Upscale binary not executable: {binary}")

        output_path = Path(context.output_path)
        if not output_path.exists():
            raise FileNotFoundError(f"Output image not found: {output_path}")

        model = os.getenv("UPSCALE_MODEL", DEFAULT_MODEL)
        scale = int(os.getenv("UPSCALE_SCALE", str(DEFAULT_SCALE)))
        timeout = int(os.getenv("UPSCALE_TIMEOUT", str(DEFAULT_TIMEOUT)))

        tmp_path = output_path.with_name(output_path.stem + ".upscale.tmp.png")

        cmd = [
            str(binary),
            "-i",
            str(output_path),
            "-o",
            str(tmp_path),
            "-n",
            model,
            "-s",
            str(scale),
        ]

        logger.info("[%s] Upscaler start: model=%s scale=%s", context.task_id, model, scale)
        start = time.perf_counter()
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout,
        )
        duration_ms = (time.perf_counter() - start) * 1000

        if not tmp_path.exists():
            raise RuntimeError(f"Upscale output missing: {tmp_path}")
        shutil.move(str(tmp_path), str(output_path))

        stderr = (result.stderr or "").lower()
        if "cpu" in stderr and "fallback" in stderr:
            logger.warning("[%s] Upscaler fallback to CPU detected", context.task_id)

        logger.info("[%s] Upscaler done: %s ms", context.task_id, int(duration_ms))
        self.last_metrics = {
            "duration_ms": round(duration_ms, 2),
            "model": model,
            "scale": scale,
        }
        return context
```

Update `core/modules/__init__.py`:

```python
from .upscaler import UpscaleModule

__all__ = [
    # ...existing
    "UpscaleModule",
]
```

**Step 4: Run the tests (expect pass)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscaler_module.py`

Expected: PASS

**Step 5: Commit**

```bash
git add core/modules/upscaler.py core/modules/__init__.py tests/test_upscaler_module.py
git commit -m "feat: add upscaler module"
```

---

### Task 2: Integrate Upscaler into pipeline

**Files:**
- Modify: `core/pipeline.py`
- Test: `tests/test_pipeline_upscaler_stage.py`

**Step 1: Write the failing test**

Create `tests/test_pipeline_upscaler_stage.py`:

```python
import asyncio
from core.modules.base import BaseModule
from core.models import TaskContext
from core.pipeline import Pipeline


class DummyModule(BaseModule):
    async def process(self, context: TaskContext) -> TaskContext:
        return context


def test_pipeline_stage_order_includes_upscaler():
    pipeline = Pipeline(
        ocr=DummyModule("ocr"),
        translator=DummyModule("translator"),
        inpainter=DummyModule("inpainter"),
        renderer=DummyModule("renderer"),
        upscaler=DummyModule("upscaler"),
    )
    stage_names = [name for name, _ in pipeline.stages]
    assert stage_names == ["ocr", "translator", "inpainter", "renderer", "upscaler"]
```

**Step 2: Run the test (expect failure)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_pipeline_upscaler_stage.py`

Expected: FAIL (Pipeline has no upscaler param).

**Step 3: Implement pipeline integration**

Modify `core/pipeline.py`:
- Import `UpscaleModule`.
- Extend `Pipeline.__init__` signature: `upscaler: Optional[BaseModule] = None`.
- Set `self.upscaler = upscaler or UpscaleModule()`.
- Add stage `("upscaler", self.upscaler)` after renderer.
- Update docstring to “OCR → Translator → Inpainter → Renderer → Upscaler”.
- In `process_batch_crosspage`, call `self.upscaler.process(ctx)` after renderer.

**Step 4: Run the test (expect pass)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_pipeline_upscaler_stage.py`

Expected: PASS

**Step 5: Commit**

```bash
git add core/pipeline.py tests/test_pipeline_upscaler_stage.py
git commit -m "feat: add upscaler stage to pipeline"
```

---

### Task 3: Local setup script + gitignore

**Files:**
- Create: `scripts/setup_local.sh`
- Modify: `.gitignore`

**Step 1: Add setup script**

Create `scripts/setup_local.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="$ROOT_DIR/tools/bin"
TMP_DIR="$(mktemp -d)"
VERSION="v0.2.0"

if [[ "$(uname -s)" == "Darwin" ]]; then
  ZIP_NAME="realesrgan-ncnn-vulkan-v0.2.0-macos.zip"
elif [[ "$(uname -s)" == "Linux" ]]; then
  ZIP_NAME="realesrgan-ncnn-vulkan-v0.2.0-ubuntu.zip"
else
  echo "Unsupported OS: $(uname -s)"
  exit 1
fi

URL="https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/${VERSION}/${ZIP_NAME}"

python -m pip install -r "$ROOT_DIR/requirements.txt"

mkdir -p "$BIN_DIR"

curl -L "$URL" -o "$TMP_DIR/$ZIP_NAME"
unzip -q "$TMP_DIR/$ZIP_NAME" -d "$TMP_DIR/extract"

BIN_SRC="$(find "$TMP_DIR/extract" -type f -name realesrgan-ncnn-vulkan | head -n 1)"
MODEL_SRC="$(find "$TMP_DIR/extract" -type d -name models | head -n 1)"

if [[ -z "$BIN_SRC" ]]; then
  echo "Binary not found in zip"
  exit 1
fi

cp "$BIN_SRC" "$BIN_DIR/realesrgan-ncnn-vulkan"
chmod +x "$BIN_DIR/realesrgan-ncnn-vulkan"

if [[ -n "$MODEL_SRC" ]]; then
  rm -rf "$BIN_DIR/models"
  cp -R "$MODEL_SRC" "$BIN_DIR/models"
fi

rm -rf "$TMP_DIR"

echo "✅ Real-ESRGAN installed to $BIN_DIR"
```

**Step 2: Add gitignore entry**

Update `.gitignore`:

```
# Tools binaries
/tools/bin/
```

**Step 3: Verify script syntax**

Run: `bash -n scripts/setup_local.sh`

Expected: no output.

**Step 4: Commit**

```bash
git add scripts/setup_local.sh .gitignore
git commit -m "chore: add local setup for realesrgan"
```

---

### Task 4: Docker download integration

**Files:**
- Modify: `docker/Dockerfile.api`
- Modify: `docker-compose.yml`

**Step 1: Update Dockerfile**

Modify `docker/Dockerfile.api`:
- Add `curl` and `unzip` to apt packages.
- Add download step for fixed version into `/opt/tools`.

```dockerfile
ARG REALESRGAN_VERSION=0.2.0

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    curl \
    unzip \
  && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/tools \
  && curl -L "https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan/releases/download/v${REALESRGAN_VERSION}/realesrgan-ncnn-vulkan-v${REALESRGAN_VERSION}-ubuntu.zip" -o /tmp/realesrgan.zip \
  && unzip -q /tmp/realesrgan.zip -d /tmp/realesrgan \
  && BIN_SRC=$(find /tmp/realesrgan -type f -name realesrgan-ncnn-vulkan | head -n 1) \
  && MODEL_SRC=$(find /tmp/realesrgan -type d -name models | head -n 1) \
  && cp "$BIN_SRC" /opt/tools/realesrgan-ncnn-vulkan \
  && chmod +x /opt/tools/realesrgan-ncnn-vulkan \
  && if [ -n "$MODEL_SRC" ]; then cp -R "$MODEL_SRC" /opt/tools/models; fi \
  && rm -rf /tmp/realesrgan /tmp/realesrgan.zip
```

**Step 2: Update docker-compose env**

Modify `docker-compose.yml`:

```yaml
environment:
  UPSCALE_BINARY_PATH: "/opt/tools/realesrgan-ncnn-vulkan"
```

**Step 3: Commit**

```bash
git add docker/Dockerfile.api docker-compose.yml
git commit -m "chore: download realesrgan binary in docker"
```

---

### Task 5: Add evaluation script + tests

**Files:**
- Create: `scripts/upscale_eval.py`
- Test: `tests/test_upscale_eval.py`

**Step 1: Write failing tests**

Create `tests/test_upscale_eval.py`:

```python
from scripts.upscale_eval import compute_stats, gain_ratio


def test_compute_stats_empty():
    stats = compute_stats([])
    assert stats["avg"] == 0.0
    assert stats["median"] == 0.0
    assert stats["count"] == 0


def test_gain_ratio():
    assert gain_ratio(0.5, 0.6) == 0.2
```

**Step 2: Run tests (expect failure)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscale_eval.py`

Expected: FAIL (script not found).

**Step 3: Implement script**

Create `scripts/upscale_eval.py`:

```python
#!/usr/bin/env python3
import argparse
import asyncio
import json
import statistics
from pathlib import Path
from datetime import datetime

from core.models import TaskContext
from core.modules.ocr import OCRModule
from core.modules.upscaler import UpscaleModule


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def compute_stats(values):
    if not values:
        return {"avg": 0.0, "median": 0.0, "count": 0}
    return {
        "avg": sum(values) / len(values),
        "median": statistics.median(values),
        "count": len(values),
    }


def gain_ratio(old, new):
    if old <= 0:
        return 0.0
    return (new - old) / old


async def ocr_confidence(image_path: Path, lang: str) -> dict:
    ocr = OCRModule(lang=lang)
    ctx = TaskContext(image_path=str(image_path), source_language=lang)
    ctx = await ocr.process(ctx)
    confs = [r.confidence for r in (ctx.regions or []) if r.confidence is not None]
    return compute_stats(confs)


async def run_eval(input_path: Path, lang: str, out_dir: Path, min_gain: float) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    upscaled_dir = out_dir / "upscaled"
    upscaled_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for image in _collect_images(input_path):
        before = await ocr_confidence(image, lang)

        # upscale to temp output
        upscaled_path = upscaled_dir / image.name
        ctx = TaskContext(image_path=str(image), output_path=str(upscaled_path))
        await UpscaleModule().process(ctx)

        after = await ocr_confidence(upscaled_path, lang)
        ratio = gain_ratio(before["avg"], after["avg"])

        results.append({
            "image": str(image),
            "upscaled": str(upscaled_path),
            "before": before,
            "after": after,
            "gain_ratio": ratio,
            "suggest_keep": ratio >= min_gain,
        })
    return results


def _collect_images(input_path: Path):
    if input_path.is_file():
        return [input_path]
    items = []
    for p in input_path.rglob("*"):
        if p.suffix.lower() in IMAGE_EXTS:
            items.append(p)
    return sorted(items)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="file or directory")
    parser.add_argument("--lang", default="korean")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    parser.add_argument("--min-gain", type=float, default=0.05)
    args = parser.parse_args()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output/upscale_eval") / ts

    results = asyncio.run(run_eval(Path(args.input), args.lang, out_dir, args.min_gain))

    if args.format == "json":
        out_path = out_dir / "report.json"
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        import csv
        out_path = out_dir / "report.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["image", "upscaled", "gain_ratio", "suggest_keep"],
            )
            writer.writeheader()
            for row in results:
                writer.writerow({
                    "image": row["image"],
                    "upscaled": row["upscaled"],
                    "gain_ratio": row["gain_ratio"],
                    "suggest_keep": row["suggest_keep"],
                })

    print(f"Report written: {out_path}")


if __name__ == "__main__":
    main()
```

**Step 4: Run tests (expect pass)**

Run: `MANHUA_LOG_DIR=$(mktemp -d) /Users/xa/Desktop/projiect/manhua/.venv/bin/python -m pytest -q tests/test_upscale_eval.py`

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/upscale_eval.py tests/test_upscale_eval.py
git commit -m "feat: add upscale evaluation script"
```

---

### Task 6: Update env template + README

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Step 1: Update .env.example**

Add section:

```env
# ===== Upscale (Real-ESRGAN, optional) =====
UPSCALE_ENABLE=0
UPSCALE_BINARY_PATH=tools/bin/realesrgan-ncnn-vulkan
UPSCALE_MODEL=realesrgan-x4plus-anime
UPSCALE_SCALE=2
UPSCALE_TIMEOUT=120
```

**Step 2: Update README.md**

- Replace local install steps with:

```bash
# 本地依赖 + Real-ESRGAN（二进制）
./scripts/setup_local.sh
```

- Add section “超分（可选）” with env vars and evaluation script usage:

```bash
UPSCALE_ENABLE=1
UPSCALE_SCALE=2
UPSCALE_MODEL=realesrgan-x4plus-anime

# 评估脚本
/Users/xa/Desktop/projiect/manhua/.venv/bin/python scripts/upscale_eval.py data/raw/sexy-woman/chapter-1/1.jpg --lang korean
```

**Step 3: Commit**

```bash
git add .env.example README.md
git commit -m "docs: document upscale settings"
```

---

## Test Plan (full)

1) `pytest -q tests/test_upscaler_module.py`
2) `pytest -q tests/test_pipeline_upscaler_stage.py`
3) `pytest -q tests/test_upscale_eval.py`
4) Manual: run `scripts/setup_local.sh` and then execute `python main.py image <img>` with `UPSCALE_ENABLE=1` to confirm output image size increases.

---

## Assumptions & Defaults
- Default upscale is **off** until `UPSCALE_ENABLE=1`.
- Fixed Real-ESRGAN-ncnn-vulkan version **v0.2.0**.
- Default model **realesrgan-x4plus-anime**, default scale **2x**.
- Output is overwritten safely via temp file + move.
- Docker uses `/opt/tools/realesrgan-ncnn-vulkan`.
