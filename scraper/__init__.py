from core.logging_config import setup_module_logger

from .base import BaseScraper, Chapter, Manga, ScraperConfig
from .downloader import AsyncDownloader, DownloadConfig, DownloadReport
from .engine import EngineConfig, ScraperEngine

setup_module_logger("scraper", "scraper.log")

__all__ = [
    "AsyncDownloader",
    "BaseScraper",
    "Chapter",
    "DownloadConfig",
    "DownloadReport",
    "EngineConfig",
    "Manga",
    "ScraperConfig",
    "ScraperEngine",
]
