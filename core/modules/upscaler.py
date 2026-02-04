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
        if tmp_path.exists():
            tmp_path.unlink()

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
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout,
                cwd=str(binary.parent),
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"Upscale timeout after {timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise RuntimeError(f"Upscale failed: {stderr[-200:]}") from exc

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
