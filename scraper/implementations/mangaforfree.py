from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import quote, urljoin, urlparse

import aiohttp

from ..base import Chapter, Manga, ScraperConfig, load_storage_state_cookies
from ..downloader import AsyncDownloader, DownloadItem
from .generic_playwright import CloudflareChallengeError, GenericPlaywrightScraper


class MangaForFreeScraper(GenericPlaywrightScraper):
    def __init__(
        self,
        config: ScraperConfig,
        downloader: AsyncDownloader | None = None,
        selectors: dict[str, str] | None = None,
    ) -> None:
        defaults = {
            "search_item": ".c-tabs-item__content, .page-item-detail",
            "search_title": ".post-title",
            "chapter_item": "li.wp-manga-chapter a, .listing-chapters_wrap a",
            "chapter_title": ".chapter-title",
            "reader_image": ".reading-content img, img.wp-manga-chapter-img",
        }
        if selectors:
            defaults.update(selectors)
        super().__init__(
            config=config,
            downloader=downloader,
            search_path="/?s={keyword}&post_type=wp-manga",
            chapter_path="/manga/{manga_id}",
            reader_path="/manga/{manga_id}/{chapter_id}/",
            selectors=defaults,
        )

    async def search_manga(self, keyword: str):
        slug = self._slugify_keyword(keyword)
        if slug:
            direct_url = urljoin(self.config.base_url, f"/manga/{slug}/")
            return [Manga(id=slug, title=keyword or slug, url=direct_url)]
        return await super().search_manga(keyword)

    async def list_catalog(  # type: ignore[override]
        self,
        page: int = 1,
        orderby: str | None = None,
        *,
        path: str | None = None,
    ):
        page = max(1, page)
        base_path = path or "/manga/"
        base_path = base_path if base_path.endswith("/") else f"{base_path}/"
        if page > 1:
            base_path = f"{base_path}page/{page}/"
        url = urljoin(self.config.base_url, base_path)
        if orderby:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}m_orderby={quote(orderby)}"
        if self.config.http_mode:
            html = await self._http_fetch_html(url)
        else:
            async with self._browser_context() as context:
                page_obj = await context.new_page()
                await page_obj.goto(
                    url, wait_until="domcontentloaded", timeout=self.config.timeout_ms
                )
                await self._guard_cloudflare(page_obj)
                await self._wait_for_search_results(page_obj)
                html = await page_obj.content()
        results = self._parse_search_results(html)
        has_more = self._has_next_page(html)
        return results, has_more

    async def get_chapters(self, manga: Manga):
        if not self.config.http_mode:
            return await super().get_chapters(manga)
        target = manga.url or urljoin(
            self.config.base_url, self.chapter_path.format(manga_id=manga.id)
        )
        html = await self._http_fetch_html(target)
        manga_id = self._extract_manga_id(html)
        if not manga_id:
            return self._parse_chapters_from_html(html)
        chapter_html = await self._http_fetch_chapters(manga_id)
        return self._parse_chapters_from_html(chapter_html)

    async def download_images(self, manga: Manga, chapter: Chapter, output_root: Path):
        if not self.config.http_mode:
            return await super().download_images(manga, chapter, output_root)

        reader_url = chapter.url or urljoin(
            self.config.base_url,
            self.reader_path.format(chapter_id=chapter.id, manga_id=manga.id),
        )
        html = await self._http_fetch_html(reader_url)
        image_urls = self._extract_image_urls_from_html(html)
        if not image_urls:
            raise RuntimeError("未找到图片，请检查 Cloudflare 或选择器。")

        items = [
            DownloadItem(
                index=index,
                url=url,
                filename=f"{index}.jpg",
                referer=reader_url,
            )
            for index, url in enumerate(image_urls, start=1)
        ]
        manifest_path = output_root / "manifest.json"
        return await self.downloader.download_all(
            items=items,
            manga=manga,
            chapter=chapter,
            output_dir=output_root,
            manifest_path=manifest_path,
            headers=self.config.extra_headers,
            cookies=self._merge_cookies(),
        )

    async def _http_fetch_html(self, url: str) -> str:
        headers = self._http_headers()
        cookies = self._merge_cookies()
        timeout = aiohttp.ClientTimeout(total=self.config.http_timeout_sec)
        async with aiohttp.ClientSession(timeout=timeout, cookies=cookies) as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                html = await response.text()
        if self._looks_like_challenge(html):
            if self._is_manga_detail_html(html):
                return html
            if self._extract_image_urls_from_html(html):
                return html
            if self._parse_search_results(html):
                return html
            raise CloudflareChallengeError(
                "检测到 Cloudflare 挑战，请先运行 bootstrap 并使用状态文件。"
            )
        return html

    async def _http_fetch_chapters(self, manga_id: str) -> str:
        headers = self._http_headers()
        cookies = self._merge_cookies()
        timeout = aiohttp.ClientTimeout(total=self.config.http_timeout_sec)
        data = {"action": "manga_get_chapters", "manga": manga_id}
        async with aiohttp.ClientSession(timeout=timeout, cookies=cookies) as session:
            async with session.post(
                urljoin(self.config.base_url, "/wp-admin/admin-ajax.php"),
                headers=headers,
                data=data,
            ) as response:
                response.raise_for_status()
                return await response.text()

    def _http_headers(self) -> dict[str, str]:
        headers = dict(self.config.extra_headers)
        if self.config.user_agent:
            headers.setdefault("User-Agent", self.config.user_agent)
        elif self.config.override_user_agent:
            headers.setdefault("User-Agent", self.user_agent_pool.pick())
        return headers

    def _merge_cookies(self) -> dict[str, str]:
        host = urlparse(self.config.base_url).hostname or ""
        cookies = load_storage_state_cookies(
            self.config.storage_state_path, domain_filter=host
        )
        if self.config.cookies:
            cookies.update(self.config.cookies)
        return cookies

    def _extract_manga_id(self, html: str) -> str | None:
        match = re.search(r"manga_id\"\s*:\s*\"(\d+)\"", html)
        if match:
            return match.group(1)
        match = re.search(r"data-id=\"(\d+)\"", html)
        if match:
            return match.group(1)
        return None
