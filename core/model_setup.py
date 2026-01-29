"""Model registry and warmup helpers for OCR/Inpainting."""

from dataclasses import dataclass
from inspect import isawaitable
from typing import Dict, Optional
import os

from core.vision.ocr.cache import get_cached_ocr
from core.vision.inpainter import create_inpainter


@dataclass
class ModelState:
    name: str
    status: str = "missing"  # missing|downloading|ready|failed
    error: Optional[str] = None


class ModelRegistry:
    def __init__(self):
        self._models = {
            "ppocr_det": ModelState(name="ppocr_det"),
            "ppocr_rec": ModelState(name="ppocr_rec"),
            "lama": ModelState(name="lama"),
        }

    def set_status(self, name: str, status: str, error: Optional[str] = None):
        if name in self._models:
            self._models[name].status = status
            self._models[name].error = error

    def snapshot(self) -> Dict[str, Dict[str, Optional[str]]]:
        return {
            name: {"status": model.status, "error": model.error}
            for name, model in self._models.items()
        }


async def _maybe_await(value):
    if isawaitable(value):
        return await value
    return value


class ModelWarmupService:
    def __init__(self, registry: ModelRegistry):
        self.registry = registry

    async def warmup(self):
        try:
            await _maybe_await(get_cached_ocr("en"))
            await _maybe_await(get_cached_ocr("korean"))
            self.registry.set_status("ppocr_det", "ready")
            self.registry.set_status("ppocr_rec", "ready")
        except Exception as exc:
            self.registry.set_status("ppocr_det", "failed", str(exc))
            self.registry.set_status("ppocr_rec", "failed", str(exc))

        try:
            device = os.getenv("LAMA_DEVICE", "cpu")
            await _maybe_await(create_inpainter(prefer_lama=True, device=device))
            self.registry.set_status("lama", "ready")
        except Exception as exc:
            self.registry.set_status("lama", "failed", str(exc))
