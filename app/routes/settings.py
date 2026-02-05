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

_UPSCALE_MODELS = {
    "realesrgan-x4plus-anime",
    "realesrgan-x4plus",
    "realesr-animevideov3-x4",
}

_UPSCALE_SCALES = {2, 4}


class ModelUpdateRequest(BaseModel):
    model: str


class SettingsResponse(BaseModel):
    source_language: str
    target_language: str
    ai_model: Optional[str]
    upscale_model: str
    upscale_scale: int


class UpscaleUpdateRequest(BaseModel):
    model: str
    scale: int


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
    
    # Also update the AITranslator instance
    from core.ai_translator import AITranslator
    
    # Update the global translator model
    try:
        # Get existing translators and update their model
        import os
        os.environ['PPIO_MODEL'] = request.model
    except Exception as e:
        print(f"Warning: Could not update environment variable: {e}")
    
    return {
        "message": f"AI model updated to {request.model}",
        "model": request.model
    }


@router.post("/upscale")
async def set_upscale_settings(request: UpscaleUpdateRequest):
    global _upscale_model_override, _upscale_scale_override

    if request.model not in _UPSCALE_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported upscale model")
    if request.scale not in _UPSCALE_SCALES:
        raise HTTPException(status_code=422, detail="Unsupported upscale scale")

    _upscale_model_override = request.model
    _upscale_scale_override = request.scale

    return {
        "message": "Upscale settings updated",
        "model": request.model,
        "scale": request.scale,
    }


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
