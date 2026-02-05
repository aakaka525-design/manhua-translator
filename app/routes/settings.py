"""
Settings API Routes.

Provides endpoints for application settings management.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from ..deps import get_settings

router = APIRouter(prefix="/settings", tags=["settings"])


# In-memory settings override (will be lost on restart)
_model_override: Optional[str] = None


class ModelUpdateRequest(BaseModel):
    model: str


class LanguageUpdateRequest(BaseModel):
    source_language: str
    target_language: str


class SettingsResponse(BaseModel):
    source_language: str
    target_language: str
    ai_model: Optional[str]


@router.get("", response_model=SettingsResponse)
async def get_current_settings(settings=Depends(get_settings)):
    """Get current application settings."""
    global _model_override
    return SettingsResponse(
        source_language=settings.source_language,
        target_language=settings.target_language,
        ai_model=_model_override or settings.ppio_model,
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
