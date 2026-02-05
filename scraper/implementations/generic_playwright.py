from __future__ import annotations

import ast
import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, cast
from urllib.parse import quote, urlparse, urljoin

from bs4 import BeautifulSoup
from playwright.async_api import BrowserContext, async_playwright

from ..base import BaseScraper, Chapter, Manga, ScraperConfig, normalize_url
from ..challenge import looks_like_challenge
from ..downloader import AsyncDownloader, DownloadConfig, DownloadItem, DownloadReport
from ..rate_limit import RequestRateLimiter


class GenericPlaywrightScraper(BaseScraper):
    def __init__(
        self,
        config: ScraperConfig,
        downloader: AsyncDownloader | None = None,
        search_path: str = "/search?q={keyword}",
        chapter_path: str = "/manga/{manga_id}",
        reader_path: str = "/chapter/{chapter_id}",
        selectors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(config)
        self.search_path = search_path
        self.chapter_path = chapter_path
        self.reader_path = reader_path
        self.selectors = {
            "search_item": "a.manga-card",
            "search_title": ".title",
            "chapter_item": "a.chapter",
            "chapter_title": ".title",
            "reader_image": "img",
        }
        if selectors:
            self.selectors.update(selectors)
        self.request_limiter = config.request_limiter or RequestRateLimiter(
            config.rate_limit_rps
        )
        self.downloader = downloader or AsyncDownloader(
            DownloadConfig(concurrency=6, rate_limit_rps=config.rate_limit_rps),
            self.user_agent_pool,
            request_limiter=self.request_limiter,
        )

    async def search_manga(self, keyword: str):
        url = urljoin(
            self.config.base_url, self.search_path.format(keyword=quote(keyword))
        )
        async with self._browser_context() as context:
            page = await context.new_page()
            await self._acquire_rate_slot()
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.config.timeout_ms
            )
            await self._guard_cloudflare(page)
            await self._wait_for_search_results(page)
            html = await self._safe_page_content(page)

        return self._parse_search_results(html)

    async def _resolve_manga_page(
        self, url: str, fallback_title: str | None = None
    ) -> Manga | None:
        async with self._browser_context() as context:
            page = await context.new_page()
            await self._acquire_rate_slot()
            await page.goto(
                url, wait_until="domcontentloaded", timeout=self.config.timeout_ms
            )
            await self._guard_cloudflare(page)
            await self._wait_for_manga_detail(page)
            html = await self._safe_page_content(page)

        if not self._is_manga_detail_html(html):
            return None
        title = self._extract_manga_title(html) or fallback_title or self._infer_id(url)
        return Manga(id=self._infer_id(url), title=title, url=url)

    def _parse_search_results(self, html: str) -> list[Manga]:
        soup = BeautifulSoup(html, "html.parser")
        results: list[Manga] = []
        for item in soup.select(self.selectors["search_item"]):
            link = item.get("href")
            if not link:
                anchor = item.select_one("a")
                link = anchor.get("href") if anchor else None
            if not link:
                continue
            title_node = item.select_one(self.selectors["search_title"])
            title = (
                title_node.get_text(strip=True)
                if title_node
                else item.get_text(strip=True)
            )
            full_url = normalize_url(self.config.base_url, str(link))
            if not self._is_manga_url(full_url):
                continue
            manga_id = self._infer_id(full_url)
            cover_url = self._extract_cover_url(item)
            results.append(
                Manga(
                    id=manga_id,
                    title=title or manga_id,
                    url=full_url,
                    cover_url=cover_url,
                )
            )

        results.extend(self._fallback_search_anchors(soup))
        return self._dedupe_manga(results)

    def _has_next_page(self, html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        selectors = [
            "a[rel='next']",
            "link[rel='next']",
            "a.page-numbers.next",
            ".page-numbers.next a",
            ".nav-links a.next",
            ".pagination a.next",
            ".nav-next a",
        ]
        for selector in selectors:
            if soup.select_one(selector):
                return True
        return False

    def _parse_chapters_from_html(self, html: str) -> list[Chapter]:
        soup = BeautifulSoup(html, "html.parser")
        items = soup.select(self.selectors["chapter_item"])
        chapters = []
        for index, item in enumerate(items, start=1):
            link = item.get("href")
            if not link:
                anchor = item.select_one("a")
                link = anchor.get("href") if anchor else None
            if not link:
                continue
            title_node = item.select_one(self.selectors["chapter_title"])
            title = (
                title_node.get_text(strip=True)
                if title_node
                else item.get_text(strip=True)
            )
            full_url = normalize_url(self.config.base_url, str(link))
            chapter_id = self._infer_id(full_url)
            chapters.append(
                Chapter(
                    id=chapter_id, title=title or chapter_id, url=full_url, index=index
                )
            )
        return chapters

    async def get_chapters(self, manga: Manga):
        target = manga.url or urljoin(
            self.config.base_url, self.chapter_path.format(manga_id=manga.id)
        )
        async with self._browser_context() as context:
            page = await context.new_page()
            await self._acquire_rate_slot()
            await page.goto(
                target, wait_until="domcontentloaded", timeout=self.config.timeout_ms
            )
            html = await self._guard_cloudflare(page)
        return self._parse_chapters_from_html(html)

    async def download_images(
        self, manga: Manga, chapter: Chapter, output_root: Path
    ) -> DownloadReport:
        async with self._browser_context() as context:
            return await self.download_images_with_context(
                context, manga, chapter, output_root
            )

    async def download_images_with_context(
        self,
        context: BrowserContext,
        manga: Manga,
        chapter: Chapter,
        output_root: Path,
    ) -> DownloadReport:
        reader_url = chapter.url or urljoin(
            self.config.base_url,
            self.reader_path.format(chapter_id=chapter.id, manga_id=manga.id),
        )
        page = await context.new_page()
        network_urls: list[str] = []

        def handle_response(response) -> None:
            if response.request.resource_type == "image":
                network_urls.append(response.url)

        page.on("response", handle_response)
        await self._acquire_rate_slot()
        await page.goto(
            reader_url,
            wait_until="domcontentloaded",
            timeout=self.config.timeout_ms,
        )
        await self._guard_cloudflare(page)
        await self._wait_for_reader_images(page)
        await self._auto_scroll(page)
        await page.wait_for_timeout(self.config.scroll_wait_ms)
        image_urls = await self._collect_image_urls(page)
        if not image_urls:
            image_urls = self._filter_network_urls(network_urls)
        await page.close()

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
            cookies=self.config.cookies,
        )

    async def _collect_image_urls(self, page) -> list[str]:
        selector = self.selectors.get("reader_image", "img")
        raw_urls = await page.evaluate(
            """
            (selector) => {
                const urls = new Set();
                const attrs = [
                    "src",
                    "data-src",
                    "data-original",
                    "data-lazy",
                    "data-url",
                    "data-srcset",
                    "data-original-src",
                    "data-lazy-src",
                ];
                const pickFromSrcset = (value) => {
                    const entries = value
                        .split(",")
                        .map((item) => item.trim().split(" ")[0])
                        .filter(Boolean);
                    return entries.length ? entries[entries.length - 1] : null;
                };
                document.querySelectorAll(selector).forEach((img) => {
                    const srcset = img.getAttribute("srcset") || img.getAttribute("data-srcset");
                    if (srcset) {
                        const chosen = pickFromSrcset(srcset);
                        if (chosen) {
                            urls.add(chosen);
                        }
                    }
                    for (const attr of attrs) {
                        const value = img.getAttribute(attr);
                        if (value) {
                            urls.add(value);
                        }
                    }
                });
                return Array.from(urls);
            }
            """,
            selector,
        )
        cleaned = []
        for url in raw_urls:
            if not url:
                continue
            if url.startswith("data:") or url.startswith("about:"):
                continue
            cleaned.append(normalize_url(self.config.base_url, url))
        deduped = self._dedupe_keep_order(cleaned)
        if deduped:
            return deduped
        html = await self._safe_page_content(page)
        script_urls = self._extract_script_image_urls(html)
        normalized = [normalize_url(self.config.base_url, url) for url in script_urls]
        return self._dedupe_keep_order(normalized)

    async def _acquire_rate_slot(self) -> None:
        await self.request_limiter.acquire()

    async def _auto_scroll(self, page) -> None:
        last_height = 0
        last_images = 0
        idle_rounds = 0
        while idle_rounds < self.config.scroll_max_idle:
            await page.evaluate(f"window.scrollBy(0, {self.config.scroll_step});")
            await page.wait_for_timeout(self.config.scroll_wait_ms)
            height = await page.evaluate("document.body.scrollHeight")
            image_count = await page.evaluate("document.images.length")
            if height == last_height and image_count == last_images:
                idle_rounds += 1
            else:
                idle_rounds = 0
                last_height = height
                last_images = image_count

    async def _wait_for_search_results(self, page) -> None:
        selectors = [
            self.selectors.get("search_item"),
            "a[href*='/webtoon/']",
            "a[href*='/manga/']",
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                await page.wait_for_selector(selector, timeout=6000)
                return
            except Exception:  # noqa: BLE001
                continue
        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:  # noqa: BLE001
            return

    async def _wait_for_manga_detail(self, page) -> None:
        selectors = [
            self.selectors.get("chapter_item"),
            "li.wp-manga-chapter a",
            ".listing-chapters_wrap a",
            "h1",
            ".post-title",
            "meta[property='og:title']",
        ]
        for selector in selectors:
            if not selector:
                continue
            try:
                await page.wait_for_selector(selector, timeout=4000)
                return
            except Exception:  # noqa: BLE001
                continue

    async def _wait_for_reader_images(self, page) -> None:
        selector = self.selectors.get("reader_image", "img")
        try:
            await page.wait_for_selector(selector, timeout=8000)
        except Exception:  # noqa: BLE001
            return

    @asynccontextmanager
    async def _browser_context(self) -> AsyncIterator[BrowserContext]:
        async with async_playwright() as playwright:
            launch_args = ["--disable-blink-features=AutomationControlled"]

            storage_state_path = (
                Path(self.config.storage_state_path)
                if self.config.storage_state_path
                else None
            )

            browser = None
            user_agent = self._pick_user_agent()

            if self.config.user_data_dir:
                user_data_dir = Path(self.config.user_data_dir)
                user_data_dir.mkdir(parents=True, exist_ok=True)
                if user_agent:
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_dir),
                        headless=self.config.headless,
                        args=launch_args,
                        channel=self.config.browser_channel,
                        user_agent=user_agent,
                        extra_http_headers=self.config.extra_headers,
                    )
                else:
                    context = await playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_data_dir),
                        headless=self.config.headless,
                        args=launch_args,
                        channel=self.config.browser_channel,
                        extra_http_headers=self.config.extra_headers,
                    )
            else:
                browser = await playwright.chromium.launch(
                    headless=self.config.headless,
                    args=launch_args,
                    channel=self.config.browser_channel,
                )
                storage_state = (
                    str(storage_state_path)
                    if storage_state_path and storage_state_path.exists()
                    else None
                )
                if user_agent and storage_state:
                    context = await browser.new_context(
                        user_agent=user_agent,
                        extra_http_headers=self.config.extra_headers,
                        storage_state=storage_state,
                    )
                elif user_agent:
                    context = await browser.new_context(
                        user_agent=user_agent,
                        extra_http_headers=self.config.extra_headers,
                    )
                elif storage_state:
                    context = await browser.new_context(
                        extra_http_headers=self.config.extra_headers,
                        storage_state=storage_state,
                    )
                else:
                    context = await browser.new_context(
                        extra_http_headers=self.config.extra_headers,
                    )

            await context.add_init_script(self._stealth_script())
            context.set_default_timeout(self.config.timeout_ms)
            if self.config.cookies:
                await context.add_cookies(cast("list[Any]", self._format_cookies()))
            try:
                yield context
            finally:
                if storage_state_path:
                    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
                    await context.storage_state(path=str(storage_state_path))
                await context.close()
                if browser:
                    await browser.close()

    def _format_cookies(self) -> list[dict[str, str]]:
        parsed = urlparse(self.config.base_url)
        domain = parsed.hostname or ""
        return [
            {"name": name, "value": value, "domain": domain, "path": "/"}
            for name, value in (self.config.cookies or {}).items()
        ]

    def _infer_id(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return path.split("/")[-1] or parsed.hostname or url

    def _dedupe_keep_order(self, items: list[str]) -> list[str]:
        seen = set()
        unique = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    def _filter_network_urls(self, urls: list[str]) -> list[str]:
        cleaned = []
        for url in urls:
            if not url:
                continue
            if url.startswith("data:") or url.startswith("about:"):
                continue
            cleaned.append(url)
        return self._dedupe_keep_order(cleaned)

    def _extract_image_urls_from_html(self, html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        selector = self.selectors.get("reader_image", "img")
        attrs = [
            "src",
            "data-src",
            "data-original",
            "data-lazy",
            "data-url",
            "data-srcset",
            "data-original-src",
            "data-lazy-src",
        ]
        urls: list[str] = []
        for img in soup.select(selector):
            srcset = img.get("srcset") or img.get("data-srcset")
            if srcset:
                chosen = self._pick_srcset_url(str(srcset))
                if chosen:
                    urls.append(chosen)
            for attr in attrs:
                value = img.get(attr)
                if value:
                    urls.append(str(value))

        urls.extend(self._extract_script_image_urls(html))
        normalized = [normalize_url(self.config.base_url, url) for url in urls]
        cleaned = [
            url
            for url in normalized
            if url and not url.startswith("data:") and not url.startswith("about:")
        ]
        return self._dedupe_keep_order(cleaned)

    def _pick_srcset_url(self, value: str) -> str | None:
        entries = [item.strip().split(" ")[0] for item in value.split(",")]
        entries = [item for item in entries if item]
        if not entries:
            return None
        return entries[-1]

    def _is_manga_detail_html(self, html: str) -> bool:
        soup = BeautifulSoup(html, "html.parser")
        chapter_selector = self.selectors.get("chapter_item")
        if chapter_selector and soup.select(chapter_selector):
            return True
        fallback_selector = "li.wp-manga-chapter a, .listing-chapters_wrap a"
        if soup.select(fallback_selector):
            return True
        return False

    def _extract_manga_title(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        selectors = [
            ".post-title",
            "h1",
            "meta[property='og:title']",
            "meta[name='title']",
        ]
        for selector in selectors:
            tag = soup.select_one(selector)
            if not tag:
                continue
            if tag.name == "meta":
                content = tag.get("content")
                if content:
                    return str(content).strip()
            else:
                text = tag.get_text(strip=True)
                if text:
                    return text
        return None

    def _fallback_search_anchors(self, soup) -> list[Manga]:
        results: list[Manga] = []
        for anchor in soup.select("a[href]"):
            href = anchor.get("href")
            if not href:
                continue
            full_url = normalize_url(self.config.base_url, str(href))
            if not self._is_manga_url(full_url):
                continue
            title = anchor.get_text(strip=True)
            if not title:
                title = anchor.get("title") or anchor.get("aria-label") or ""
            if not title:
                img = anchor.find("img")
                if img:
                    title = img.get("alt") or ""
            manga_id = self._infer_id(full_url)
            cover_url = self._extract_cover_url(anchor)
            results.append(
                Manga(
                    id=manga_id,
                    title=title or manga_id,
                    url=full_url,
                    cover_url=cover_url,
                )
            )
        return results

    def _extract_cover_url(self, node) -> str | None:
        if not node:
            return None
        img = node.select_one("img") if hasattr(node, "select_one") else None
        if not img:
            return None
        attrs = [
            "data-src",
            "data-original",
            "data-lazy",
            "data-srcset",
            "data-lazy-src",
            "data-original-src",
            "srcset",
            "src",
        ]
        for attr in attrs:
            value = img.get(attr)
            if not value:
                continue
            if attr in {"srcset", "data-srcset"}:
                chosen = self._pick_srcset_url(str(value))
                if chosen:
                    value = chosen
                else:
                    continue
            url = str(value).strip()
            if not url or url.startswith("data:") or url.startswith("about:"):
                continue
            return normalize_url(self.config.base_url, url)
        return None

    def _is_manga_url(self, url: str) -> bool:
        path = urlparse(url).path.lower().strip("/")
        if not path:
            return False
        if "/chapter" in path or "chapter-" in path:
            return False
        if path.startswith("manga-genre") or path.startswith("webtoon-genre"):
            return False
        segments = path.split("/")
        if "manga" in segments:
            idx = segments.index("manga")
            if idx == len(segments) - 1:
                return False
            if segments[idx + 1] in {"page", "genre", "category", "tag"}:
                return False
            return True
        if "webtoon" in segments:
            idx = segments.index("webtoon")
            if idx == len(segments) - 1:
                return False
            if segments[idx + 1] in {"page", "genre", "category", "tag"}:
                return False
            return True
        return False

    def _dedupe_manga(self, items: list[Manga]) -> list[Manga]:
        seen = set()
        unique: list[Manga] = []
        for item in items:
            key = item.url or item.id
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    def _slugify_keyword(self, keyword: str) -> str:
        value = keyword.strip().lower().replace("_", " ")
        value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
        value = re.sub(r"[\s\-]+", "-", value)
        return value.strip("-")

    def _extract_script_image_urls(self, html: str) -> list[str]:
        patterns = (
            r"chapter_preloaded_images\s*=\s*(\[[^\]]+\])",
            r"chapter_images\s*=\s*(\[[^\]]+\])",
            r"images\s*:\s*(\[[^\]]+\])",
        )
        for pattern in patterns:
            match = re.search(pattern, html, flags=re.S)
            if not match:
                continue
            urls = self._parse_js_array(match.group(1))
            if urls:
                return urls
        return []

    def _parse_js_array(self, raw: str) -> list[str]:
        payload = raw.strip().rstrip(";")
        for parser in (json.loads, ast.literal_eval):
            try:
                data = parser(payload)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(data, list):
                return [str(item) for item in data if isinstance(item, str)]
        cleaned = payload.replace("'", '"')
        try:
            data = json.loads(cleaned)
        except Exception:  # noqa: BLE001
            return []
        if isinstance(data, list):
            return [str(item) for item in data if isinstance(item, str)]
        return []

    async def _guard_cloudflare(self, page) -> str:
        waited = 0
        poll_ms = max(200, self.config.challenge_poll_ms)
        while True:
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=poll_ms)
                html = await self._safe_page_content(page)
            except Exception:  # noqa: BLE001
                if waited >= self.config.challenge_wait_ms:
                    handled = await self._maybe_manual_challenge(page)
                    if handled:
                        html = await self._safe_page_content(page)
                        if not self._looks_like_challenge(html):
                            return html
                    raise CloudflareChallengeError(
                        "检测到 Cloudflare 挑战，请先运行 bootstrap 并使用状态文件。"
                    )
                await page.wait_for_timeout(poll_ms)
                waited += poll_ms
                continue

            if not self._looks_like_challenge(html):
                return html
            if waited >= self.config.challenge_wait_ms:
                handled = await self._maybe_manual_challenge(page)
                if handled:
                    html = await self._safe_page_content(page)
                    if not self._looks_like_challenge(html):
                        return html
                raise CloudflareChallengeError(
                    "检测到 Cloudflare 挑战，请先运行 bootstrap 并使用状态文件。"
                )
            await page.wait_for_timeout(poll_ms)
            waited += poll_ms

    async def _maybe_manual_challenge(self, page) -> bool:
        if self.config.headless or not self.config.manual_challenge:
            return False
        return await self._wait_for_challenge_clear(page, self.config.challenge_wait_ms)

    async def _wait_for_challenge_clear(self, page, timeout_ms: int) -> bool:
        poll_ms = max(500, self.config.challenge_poll_ms)
        waited = 0
        warned = False
        while waited <= timeout_ms:
            await page.wait_for_timeout(poll_ms)
            try:
                html = await self._safe_page_content(page)
            except Exception:  # noqa: BLE001
                waited += poll_ms
                continue
            if not self._looks_like_challenge(html):
                return True
            if not warned:
                warned = True
            waited += poll_ms
        return False

    def _pick_user_agent(self) -> str | None:
        if not self.config.override_user_agent:
            return None
        return self.config.user_agent or self.user_agent_pool.pick()

    async def _safe_page_content(self, page, attempts: int = 3) -> str:
        last_error = None
        for _ in range(max(1, attempts)):
            try:
                return await page.content()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=self.config.challenge_poll_ms
                    )
                except Exception:  # noqa: BLE001
                    pass
                await page.wait_for_timeout(max(200, self.config.challenge_poll_ms))
        raise last_error

    def _looks_like_challenge(self, html: str) -> bool:
        return looks_like_challenge(html)

    def _stealth_script(self) -> str:
        return """
            () => {
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
                window.chrome = window.chrome || { runtime: {} };
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (parameters) => (
                    parameters.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : originalQuery(parameters)
                );
            }
        """


class CloudflareChallengeError(RuntimeError):
    pass
