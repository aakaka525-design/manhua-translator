import asyncio
import logging
import os
import subprocess
import sys
import time
import types
import importlib.util
from pathlib import Path

import cv2

from .base import BaseModule
from ..models import TaskContext
from ..image_io import save_image

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "realesrgan-x4plus-anime"
DEFAULT_SCALE = 2
DEFAULT_TIMEOUT = 120
DEFAULT_BACKEND = "pytorch"
DEFAULT_PYTORCH_MODEL = "tools/bin/RealESRGAN_x4plus.pth"
DEFAULT_TILE = 0
DEFAULT_DEVICE = "auto"
DEFAULT_STRIPE_ENABLE = "0"
DEFAULT_STRIPE_THRESHOLD = 4000
DEFAULT_STRIPE_HEIGHT = 2000
DEFAULT_STRIPE_OVERLAP = 64


def _override_upscale_model() -> str | None:
    try:
        from app.routes.settings import get_current_upscale_model
    except Exception:
        return None
    try:
        return get_current_upscale_model()
    except Exception:
        return None


def _override_upscale_scale() -> int | None:
    try:
        from app.routes.settings import get_current_upscale_scale
    except Exception:
        return None
    try:
        return get_current_upscale_scale()
    except Exception:
        return None


def _override_upscale_enable() -> bool | None:
    try:
        from app.routes.settings import get_current_upscale_enable
    except Exception:
        return None
    try:
        return get_current_upscale_enable()
    except Exception:
        return None


def _ensure_torchvision_functional_tensor() -> None:
    if "torchvision.transforms.functional_tensor" in sys.modules:
        return
    spec = None
    try:
        spec = importlib.util.find_spec("torchvision.transforms.functional_tensor")
    except (ValueError, ModuleNotFoundError):
        spec = None
    if spec is not None:
        return
    try:
        from torchvision.transforms import functional as functional_api
    except Exception:
        return
    module = types.ModuleType("torchvision.transforms.functional_tensor")
    if hasattr(functional_api, "rgb_to_grayscale"):
        module.rgb_to_grayscale = functional_api.rgb_to_grayscale
    sys.modules["torchvision.transforms.functional_tensor"] = module


def _resolve_torch_device_name() -> str:
    choice = os.getenv("UPSCALE_DEVICE", DEFAULT_DEVICE).strip().lower()
    if choice not in {"auto", "mps", "cpu"}:
        raise ValueError(f"Unsupported UPSCALE_DEVICE: {choice}")
    try:
        import torch
    except Exception as exc:
        raise ImportError("Missing torch for UPSCALE_DEVICE resolution") from exc

    mps_backend = getattr(torch.backends, "mps", None)
    mps_available = bool(mps_backend and mps_backend.is_available())

    if choice == "mps":
        if not mps_available:
            raise RuntimeError("UPSCALE_DEVICE=mps but MPS is not available")
        return "mps"
    if choice == "cpu":
        return "cpu"
    return "mps" if mps_available else "cpu"


def compute_stripes(height: int, threshold: int, stripe_height: int, overlap: int) -> list[tuple[int, int]]:
    if height <= threshold:
        return [(0, height)]
    if stripe_height <= overlap:
        raise ValueError("stripe_height must be greater than overlap")
    stripes: list[tuple[int, int]] = []
    start = 0
    while start < height:
        end = min(start + stripe_height, height)
        remaining = height - end
        if remaining > 0 and remaining < overlap:
            end = height
        stripes.append((start, end))
        if end >= height:
            break
        start = end - overlap
    return stripes


def crop_and_merge(stripes: list, overlap_px: int, scale: int):
    import numpy as np

    if not stripes:
        raise ValueError("no stripes to merge")
    if len(stripes) == 1 or overlap_px <= 0:
        return np.concatenate(stripes, axis=0) if len(stripes) > 1 else stripes[0]
    trimmed = []
    for idx, stripe in enumerate(stripes):
        if stripe.shape[0] <= overlap_px:
            raise ValueError("stripe height too small for overlap")
        if idx == 0:
            trimmed.append(stripe[:-overlap_px])
        elif idx == len(stripes) - 1:
            trimmed.append(stripe[overlap_px:])
        else:
            if stripe.shape[0] <= 2 * overlap_px:
                raise ValueError("stripe height too small for double overlap")
            trimmed.append(stripe[overlap_px:-overlap_px])
    return np.concatenate(trimmed, axis=0)


class UpscaleModule(BaseModule):
    def __init__(self, binary_path: str | None = None):
        super().__init__(name="Upscaler")
        self.binary_path = Path(binary_path) if binary_path else None
        self.last_metrics: dict | None = None

    def _enabled(self) -> bool:
        override = _override_upscale_enable()
        if override is not None:
            return override
        return os.getenv("UPSCALE_ENABLE", "0").strip().lower() in {"1", "true", "yes", "on"}

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

    def _resolve_pytorch_model(self) -> Path:
        model_path = os.getenv("UPSCALE_MODEL_PATH", DEFAULT_PYTORCH_MODEL)
        return Path(model_path)

    def _backend(self) -> str:
        return os.getenv("UPSCALE_BACKEND", DEFAULT_BACKEND).strip().lower()

    async def process(self, context: TaskContext) -> TaskContext:
        if not self._enabled():
            return context
        if not context.output_path:
            logger.warning("[%s] Upscaler skipped: no output_path", context.task_id)
            return context

        output_path = Path(context.output_path)
        if not output_path.exists():
            raise FileNotFoundError(f"Output image not found: {output_path}")

        backend = self._backend()
        if backend == "pytorch":
            # Offload heavy torch inference to a worker thread so API loop stays responsive.
            return await asyncio.to_thread(self._run_pytorch, context, output_path)
        if backend == "ncnn":
            # Offload blocking subprocess call (ncnn) to avoid blocking the event loop.
            return await asyncio.to_thread(self._run_ncnn, context, output_path)
        raise ValueError(f"Unsupported UPSCALE_BACKEND: {backend}")

    def _run_ncnn(self, context: TaskContext, output_path: Path) -> TaskContext:
        binary = self._resolve_binary().expanduser().resolve()
        if not binary.exists():
            raise FileNotFoundError(
                f"Upscale binary not found: {binary}. Run scripts/setup_local.sh or rebuild Docker image."
            )
        if not os.access(binary, os.X_OK):
            raise PermissionError(f"Upscale binary not executable: {binary}")

        model = _override_upscale_model() or os.getenv("UPSCALE_MODEL", DEFAULT_MODEL)
        model_dir = Path(os.getenv("UPSCALE_NCNN_MODEL_DIR", "tools/bin/models")).expanduser().resolve()
        if not model_dir.exists():
            raise FileNotFoundError(
                f"Upscale model dir not found: {model_dir}. Provide UPSCALE_NCNN_MODEL_DIR or run scripts/setup_local.sh."
            )
        scale = _override_upscale_scale() or int(os.getenv("UPSCALE_SCALE", str(DEFAULT_SCALE)))
        tile = int(os.getenv("UPSCALE_TILE", str(DEFAULT_TILE)))
        timeout = int(os.getenv("UPSCALE_TIMEOUT", str(DEFAULT_TIMEOUT)))

        input_path = output_path.resolve()
        input_tmp = None
        output_tmp = None

        if output_path.suffix.lower() == ".webp":
            input_tmp = output_path.with_name(output_path.stem + ".upscale.in.png").resolve()
            output_tmp = output_path.with_name(output_path.stem + ".upscale.tmp.png").resolve()
            image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"Failed to read image: {input_path}")
            cv2.imwrite(str(input_tmp), image)
            input_path = input_tmp
            tmp_path = output_tmp
        else:
            tmp_path = output_path.with_name(
                output_path.stem + ".upscale.tmp" + output_path.suffix
            ).resolve()

        if tmp_path.exists():
            tmp_path.unlink()

        cmd = [
            str(binary),
            "-i",
            str(input_path),
            "-o",
            str(tmp_path),
            "-m",
            str(model_dir),
            "-n",
            model,
            "-s",
            str(scale),
        ]
        if tile > 0:
            cmd.extend(["-t", str(tile)])

        logger.info(
            "[%s] Upscaler start (ncnn): model=%s scale=%s tile=%s",
            context.task_id,
            model,
            scale,
            tile,
        )
        overall_start = time.perf_counter()
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

        duration_ms = (time.perf_counter() - overall_start) * 1000

        if not tmp_path.exists():
            raise RuntimeError(f"Upscale output missing: {tmp_path}")

        image = cv2.imread(str(tmp_path), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError(f"Failed to read image: {tmp_path}")
        saved_path = save_image(image, str(output_path), purpose="final")
        output_path = Path(saved_path)

        if tmp_path.exists():
            tmp_path.unlink()
        if output_tmp and output_tmp.exists():
            output_tmp.unlink()
        if input_tmp and input_tmp.exists():
            input_tmp.unlink()

        stderr = (result.stderr or "").lower()
        if "cpu" in stderr and "fallback" in stderr:
            logger.warning("[%s] Upscaler fallback to CPU detected", context.task_id)

        logger.info("[%s] Upscaler done: %s ms", context.task_id, int(duration_ms))
        self.last_metrics = {
            "duration_ms": round(duration_ms, 2),
            "model": model,
            "scale": scale,
            "tile": tile,
            "backend": "ncnn",
        }
        context.output_path = str(output_path)
        return context

    def _run_pytorch(self, context: TaskContext, output_path: Path) -> TaskContext:
        model_path = self._resolve_pytorch_model()
        if not model_path.exists():
            raise FileNotFoundError(
                f"Upscale model not found: {model_path}. Provide UPSCALE_MODEL_PATH or run scripts/setup_local.sh."
            )

        _ensure_torchvision_functional_tensor()
        try:
            import torch
            import cv2
            from basicsr.archs.rrdbnet_arch import RRDBNet
            from realesrgan import RealESRGANer
        except Exception as exc:
            raise ImportError(
                "Missing PyTorch upscale deps. Install with: pip install torch torchvision realesrgan basicsr"
            ) from exc

        scale = _override_upscale_scale() or int(os.getenv("UPSCALE_SCALE", str(DEFAULT_SCALE)))
        timeout = int(os.getenv("UPSCALE_TIMEOUT", str(DEFAULT_TIMEOUT)))
        tile = int(os.getenv("UPSCALE_TILE", str(DEFAULT_TILE)))

        tmp_path = output_path.with_name(
            output_path.stem + ".upscale.tmp" + output_path.suffix
        )
        if tmp_path.exists():
            tmp_path.unlink()

        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64, num_block=23, num_grow_ch=32, scale=4)
        device_name = _resolve_torch_device_name()
        device = torch.device(device_name)
        upsampler = RealESRGANer(
            scale=4,
            model_path=str(model_path),
            model=model,
            tile=tile,
            tile_pad=10,
            pre_pad=0,
            half=False,
            device=device,
        )

        logger.info(
            "[%s] Upscaler start (pytorch): model=%s scale=%s tile=%s device=%s",
            context.task_id,
            model_path.name,
            scale,
            tile,
            device_name,
        )
        overall_start = time.perf_counter()
        try:
            image = cv2.imread(str(output_path), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError(f"Failed to read image: {output_path}")
            stripe_enable = os.getenv("UPSCALE_STRIPE_ENABLE", DEFAULT_STRIPE_ENABLE) == "1"
            threshold = int(os.getenv("UPSCALE_STRIPE_THRESHOLD", str(DEFAULT_STRIPE_THRESHOLD)))
            stripe_height = int(os.getenv("UPSCALE_STRIPE_HEIGHT", str(DEFAULT_STRIPE_HEIGHT)))
            overlap = int(os.getenv("UPSCALE_STRIPE_OVERLAP", str(DEFAULT_STRIPE_OVERLAP)))

            if stripe_enable and image.shape[0] > threshold:
                stripes = compute_stripes(image.shape[0], threshold, stripe_height, overlap)
                logger.info(
                    "stripe: segments=%d h=%d threshold=%d overlap=%d",
                    len(stripes),
                    image.shape[0],
                    threshold,
                    overlap,
                )
                outputs = []
                overlap_px = int(overlap * scale)
                for i, (stripe_start, stripe_end) in enumerate(stripes):
                    stripe = image[stripe_start:stripe_end, :, :]
                    start_t = time.perf_counter()
                    try:
                        out, _ = upsampler.enhance(stripe, outscale=scale)
                    except Exception as exc:
                        logger.error(
                            "stripe[%d] failed: input_size=%sx%s error=%s",
                            i,
                            stripe.shape[1],
                            stripe.shape[0],
                            exc,
                        )
                        raise RuntimeError(f"Stripe {i} upscale failed") from exc
                    elapsed = (time.perf_counter() - start_t) * 1000
                    logger.debug(
                        "stripe[%d]: input_h=%d output_h=%d ms=%.0f",
                        i,
                        stripe.shape[0],
                        out.shape[0],
                        elapsed,
                    )
                    outputs.append(out)
                output = crop_and_merge(outputs, overlap_px=overlap_px, scale=scale)
            else:
                output, _ = upsampler.enhance(image, outscale=scale)
        except Exception as exc:
            raise RuntimeError(f"Upscale failed: {exc}") from exc

        duration_ms = (time.perf_counter() - overall_start) * 1000
        if duration_ms > timeout * 1000:
            raise TimeoutError(f"Upscale timeout after {timeout}s")

        saved_path = save_image(output, str(output_path), purpose="final")
        output_path = Path(saved_path)

        logger.info("[%s] Upscaler done: %s ms", context.task_id, int(duration_ms))
        self.last_metrics = {
            "duration_ms": round(duration_ms, 2),
            "model": model_path.name,
            "scale": scale,
            "backend": "pytorch",
        }
        context.output_path = str(output_path)
        return context
