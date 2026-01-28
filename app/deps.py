"""
Dependency injection for FastAPI.

Provides shared resources and configuration across routes.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings

from core.pipeline import Pipeline
from core.modules import OCRModule, TranslatorModule, InpainterModule, RendererModule


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # API Keys
    openai_api_key: Optional[str] = None
    deepl_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ppio_api_key: Optional[str] = None
    ppio_base_url: Optional[str] = None
    ppio_model: Optional[str] = None

    # Translation settings
    source_language: str = "korean"  # 默认韩语 OCR
    target_language: str = "zh"

    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # Storage paths
    data_dir: str = "./data"
    output_dir: str = "./output"
    temp_dir: str = "./temp"
    static_dir: str = "./app/static"
    templates_dir: str = "./app/templates"

    # Scraper auth
    scraper_auth_url: Optional[str] = None

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global pipeline instance
_pipeline_instance: Pipeline = None


def get_pipeline() -> Pipeline:
    """Get pipeline instance with language-aware OCR."""
    global _pipeline_instance
    if _pipeline_instance is None:
        settings = get_settings()
        _pipeline_instance = Pipeline(
            ocr=OCRModule(lang=settings.source_language),
            translator=TranslatorModule(),
            inpainter=InpainterModule(output_dir=settings.temp_dir),  # 副产品到 temp
            renderer=RendererModule(output_dir=settings.output_dir),  # 成品到 output
        )
    return _pipeline_instance
