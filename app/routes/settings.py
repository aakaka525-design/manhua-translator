"""
Settings API Routes.

Provides endpoints for application settings management.
"""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..deps import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


# In-memory settings overrides (will be lost on restart)
_model_override: Optional[str] = None
_upscale_model_override: Optional[str] = None
_upscale_scale_override: Optional[int] = None
_upscale_enable_override: Optional[bool] = None

_UPSCALE_MODELS = {
    "realesrgan-x4plus-anime",
    "realesrgan-x4plus",
    "realesr-animevideov3-x4",
}

_UPSCALE_SCALES = {2, 4}


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

    if request.model not in _UPSCALE_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported upscale model")
    if request.scale not in _UPSCALE_SCALES:
        raise HTTPException(status_code=422, detail="Unsupported upscale scale")

    _upscale_model_override = request.model
    _upscale_scale_override = request.scale
    if request.enabled is not None:
        _upscale_enable_override = request.enabled

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
    if _upscale_model_override:
        return _upscale_model_override
    return os.getenv("UPSCALE_MODEL", "realesrgan-x4plus-anime")


def get_current_upscale_scale() -> int:
    if _upscale_scale_override is not None:
        return _upscale_scale_override
    try:
        return int(os.getenv("UPSCALE_SCALE", "2"))
    except ValueError:
        return 2


def get_current_upscale_enable() -> bool:
    if _upscale_enable_override is not None:
        return _upscale_enable_override
    return os.getenv("UPSCALE_ENABLE", "0").strip().lower() in {"1", "true", "yes", "on"}
