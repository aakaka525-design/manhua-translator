from __future__ import annotations

import logging
from typing import Sequence, cast
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin
from urllib.robotparser import RobotFileParser

import aiohttp

from .base import BaseScraper, Chapter, Manga, safe_name


@dataclass
class EngineConfig:
    output_root: Path = Path("data/raw")


class ScraperEngine:
    def __init__(
        self, scraper: BaseScraper, config: EngineConfig | None = None
    ) -> None:
        self.scraper = scraper
        self.config = config or EngineConfig()
        self.logger = logging.getLogger(__name__)

    async def search(self, keyword: str):
        self.logger.info("search start | keyword=%s", keyword)
        results = await self.scraper.search_manga(keyword)
        self.logger.info("search done | keyword=%s results=%s", keyword, len(results))
        return results

    async def list_chapters(self, manga: Manga):
        self.logger.info("list chapters | manga=%s", manga.title or manga.id)
        chapters = await self.scraper.get_chapters(manga)
        self.logger.info(
            "chapters done | manga=%s count=%s", manga.title or manga.id, len(chapters)
        )
        return chapters

    async def list_catalog(
        self,
        page: int = 1,
        orderby: str | None = None,
        path: str | None = None,
    ) -> tuple[Sequence[Manga], bool]:
        if not hasattr(self.scraper, "list_catalog"):
            raise NotImplementedError("catalog is not supported")
        self.logger.info(
            "list catalog | page=%s orderby=%s path=%s",
            page,
            orderby or "default",
            path or "default",
        )
        result = await self.scraper.list_catalog(page=page, orderby=orderby, path=path)
        has_more = False
        if (
            isinstance(result, tuple)
            and len(result) == 2
            and isinstance(result[1], bool)
        ):
            items = list(cast(Sequence[Manga], result[0]))
            has_more = result[1]
        else:
            items = list(cast(Sequence[Manga], result))
        count = len(items)
        self.logger.info("catalog done | page=%s count=%s", page, count)
        return items, has_more

    async def download_chapter(self, manga: Manga, chapter: Chapter):
        manga_dir = safe_name(manga.id or manga.title)
        chapter_dir = safe_name(chapter.id or chapter.title)
        output_root = self.config.output_root / manga_dir / chapter_dir
        self.logger.info(
            "download start | manga=%s chapter=%s output=%s",
            manga.title or manga.id,
            chapter.title or chapter.id,
            output_root,
        )
        try:
            report = await self.scraper.download_images(manga, chapter, output_root)
        except Exception as exc:  # noqa: BLE001
            self.logger.exception(
                "download failed | manga=%s chapter=%s error=%s",
                manga.title or manga.id,
                chapter.title or chapter.id,
                exc,
            )
            raise
        self.logger.info(
            "download done | manga=%s chapter=%s success=%s failed=%s output=%s",
            manga.title or manga.id,
            chapter.title or chapter.id,
            report.success_count,
            report.failed_count,
            report.output_dir,
        )
        return report

    async def download_manga(self, manga: Manga):
        self.logger.info("download manga | manga=%s", manga.title or manga.id)
        chapters = await self.list_chapters(manga)
        reports = []
        for chapter in chapters:
            reports.append(await self.download_chapter(manga, chapter))
        self.logger.info(
            "download manga done | manga=%s chapters=%s",
            manga.title or manga.id,
            len(reports),
        )
        return reports

    async def advise_robots(self, path: str = "/", user_agent: str = "*") -> bool:
        robots_url = urljoin(self.scraper.config.base_url, "/robots.txt")
        target_url = urljoin(self.scraper.config.base_url, path)
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession() as session:
                async with session.get(robots_url, timeout=timeout) as response:
                    if response.status >= 400:
                        return True
                    content = await response.text()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning("robots.txt fetch failed: %s", exc)
            return True

        parser = RobotFileParser()
        parser.parse(content.splitlines())
        allowed = parser.can_fetch(user_agent, target_url)
        if not allowed:
            self.logger.warning("robots.txt disallows %s", target_url)
        return allowed
