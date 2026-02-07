"""
Settings API Routes.

Provides endpoints for application settings management.
"""

import os
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..deps import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger(__name__)


# In-memory settings overrides (will be lost on restart)
_model_override: Optional[str] = None
_upscale_model_override: Optional[str] = None
_upscale_scale_override: Optional[int] = None
_upscale_enable_override: Optional[bool] = None

_UPSCALE_MODEL_SCALES = {
    "realesrgan-x4plus-anime": {4},
    "realesrgan-x4plus": {4},
    "realesr-animevideov3-x2": {2},
    "realesr-animevideov3-x3": {3},
    "realesr-animevideov3-x4": {4},
}


class ModelUpdateRequest(BaseModel):
    model: str


class LanguageUpdateRequest(BaseModel):
    source_language: str
    target_language: str


class SettingsResponse(BaseModel):
    source_language: str
    target_language: str
    ai_model: Optional[str]
    upscale_model: str
    upscale_scale: int
    upscale_enable: bool


class UpscaleUpdateRequest(BaseModel):
    model: str
    scale: int
    enabled: Optional[bool] = None


@router.get("", response_model=SettingsResponse)
async def get_current_settings(settings=Depends(get_settings)):
    """Get current application settings."""
    global _model_override
    return SettingsResponse(
        source_language=settings.source_language,
        target_language=settings.target_language,
        ai_model=_model_override or settings.ppio_model,
        upscale_model=get_current_upscale_model(),
        upscale_scale=get_current_upscale_scale(),
        upscale_enable=get_current_upscale_enable(),
    )


@router.post("/model")
async def set_ai_model(request: ModelUpdateRequest):
    """
    Update the AI model used for translation.
    
    This is a runtime override that will be lost on restart.
    For persistent changes, update the .env file.
    """
    global _model_override
    _model_override = request.model

    return {
        "message": f"AI model updated to {request.model}",
        "model": request.model
    }


@router.post("/upscale")
async def set_upscale_settings(request: UpscaleUpdateRequest):
    global _upscale_model_override, _upscale_scale_override, _upscale_enable_override

    allowed_scales = _UPSCALE_MODEL_SCALES.get(request.model)
    if allowed_scales is None:
        raise HTTPException(status_code=422, detail="Unsupported upscale model")
    if request.scale not in allowed_scales:
        raise HTTPException(status_code=422, detail="Unsupported upscale scale for model")

    _upscale_model_override = request.model
    _upscale_scale_override = request.scale
    if request.enabled is not None:
        _upscale_enable_override = request.enabled

    logger.info(
        "Upscale settings updated: model=%s scale=%s enabled=%s (effective_enabled=%s)",
        request.model,
        request.scale,
        request.enabled,
        get_current_upscale_enable(),
    )

    return {
        "message": "Upscale settings updated",
        "model": request.model,
        "scale": request.scale,
        "enabled": get_current_upscale_enable(),
    }


@router.post("/language")
async def update_language(request: LanguageUpdateRequest, settings=Depends(get_settings)):
    """Update runtime language settings and persist to .env."""
    settings.source_language = request.source_language
    settings.target_language = request.target_language

    from app.utils.env_file import update_env_file

    update_env_file("SOURCE_LANGUAGE", request.source_language)
    update_env_file("TARGET_LANGUAGE", request.target_language)

    return {"status": "ok"}


def get_current_model() -> Optional[str]:
    """Get the current model override (for use by other modules)."""
    return _model_override


def get_current_upscale_model() -> str:
    model = _upscale_model_override or os.getenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")
    if model not in _UPSCALE_MODEL_SCALES:
        return "realesrgan-x4plus-anime"
    return model


def get_current_upscale_scale() -> int:
    model = get_current_upscale_model()
    allowed_scales = _UPSCALE_MODEL_SCALES[model]

    if _upscale_scale_override is not None:
        if _upscale_scale_override in allowed_scales:
            return _upscale_scale_override
        return min(allowed_scales)

    try:
        scale = int(os.getenv("UPSCALE_SCALE", "2"))
    except ValueError:
        return min(allowed_scales)

    if scale in allowed_scales:
        return scale
    return min(allowed_scales)


def get_current_upscale_enable() -> bool:
    if _upscale_enable_override is not None:
        return _upscale_enable_override
    return os.getenv("UPSCALE_ENABLE", "0").strip().lower() in {"1", "true", "yes", "on"}
