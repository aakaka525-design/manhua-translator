"""ToonGod 爬虫简易 GUI。"""

from __future__ import annotations

import asyncio
import re
import threading
import sys
from pathlib import Path
from typing import Any, Coroutine

import tkinter as tk
from tkinter import ttk

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import Chapter, EngineConfig, Manga, ScraperConfig, ScraperEngine
from scraper.base import DEFAULT_USER_AGENTS, safe_name
from scraper.downloader import AsyncDownloader, DownloadConfig
from scraper.implementations import MangaForFreeScraper, ToonGodScraper
from scraper.implementations.generic_playwright import CloudflareChallengeError
from scraper.url_utils import infer_id as _infer_id
from scraper.url_utils import infer_url as _infer_url
from scraper.url_utils import normalize_base_url as _normalize_base_url
from scraper.url_utils import parse_chapter_range as _parse_chapter_range
from scraper.url_utils import slugify_keyword as _slugify_keyword


DEFAULT_BASE_URL = "https://toongod.org"
DEFAULT_OUTPUT_ROOT = "data/raw"
DEFAULT_STORAGE_STATE = "data/toongod_state.json"
DEFAULT_PROFILE_DIR = "data/playwright_profile"
DEFAULT_CHANNEL = "chrome"
DEFAULT_CONCURRENCY = 6
DEFAULT_CHALLENGE_WAIT_MS = 60000


def _select_scraper(base_url: str, config: ScraperConfig, downloader: AsyncDownloader):
    if "mangaforfree.com" in base_url:
        return MangaForFreeScraper(config, downloader=downloader)
    return ToonGodScraper(config, downloader=downloader)


def _extract_chapter_number(value: str) -> float | None:
    lowered = value.lower()
    decimal_match = re.search(r"(\d+\.\d+)", lowered)
    if decimal_match:
        try:
            return float(decimal_match.group(1))
        except ValueError:
            return None

    chapter_hint = re.search(r"\b(chapter|chap|ch|episode|ep)\b", lowered)
    hyphen_match = re.search(r"(\d+)[-_](\d+)", lowered)
    if hyphen_match and (chapter_hint or re.match(r"^\d+[-_]\d+$", lowered)):
        try:
            return float(f"{hyphen_match.group(1)}.{hyphen_match.group(2)}")
        except ValueError:
            return None

    number_match = re.search(r"(\d+)", lowered)
    if not number_match:
        return None
    try:
        return float(number_match.group(1))
    except ValueError:
        return None


def _find_chapter_by_number(chapters: list[Chapter], number: float) -> Chapter | None:
    for chapter in chapters:
        candidate = _extract_chapter_number(chapter.id) or _extract_chapter_number(
            chapter.title
        )
        if candidate is None:
            continue
        if abs(candidate - number) < 1e-6:
            return chapter
    return None


def _select_chapters_by_range(
    chapters: list[Chapter], start: float, end: float
) -> list[Chapter]:
    numeric_items: list[tuple[float, Chapter]] = []
    for chapter in chapters:
        candidate = _extract_chapter_number(chapter.id) or _extract_chapter_number(
            chapter.title
        )
        if candidate is None:
            continue
        numeric_items.append((candidate, chapter))

    if numeric_items:
        matched = [item for item in numeric_items if start <= item[0] <= end]
        if not matched:
            raise RuntimeError("未找到指定章节范围")
        matched.sort(key=lambda item: item[0])
        return [item[1] for item in matched]

    if start.is_integer() and end.is_integer():
        start_idx = int(start)
        end_idx = int(end)
        return list(chapters[start_idx - 1 : end_idx])

    raise RuntimeError("章节范围无法匹配")


class ScraperGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("ToonGod 爬虫工具")
        self.root.geometry("780x560")
        self.bootstrap_event = threading.Event()
        self.stop_event = threading.Event()
        self.active_loop: asyncio.AbstractEventLoop | None = None
        self.active_task: asyncio.Task | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Label(
            container,
            text="输入漫画名和章节即可开始下载",
            font=("TkDefaultFont", 12),
        )
        header.pack(anchor="w", pady=(0, 12))

        bootstrap_frame = ttk.LabelFrame(
            container, text="Cloudflare 初始化", padding=12
        )
        bootstrap_frame.pack(fill=tk.X)

        self.bootstrap_btn = ttk.Button(
            bootstrap_frame, text="启动 Bootstrap", command=self._start_bootstrap
        )
        self.bootstrap_btn.pack(side=tk.LEFT)

        self.finish_bootstrap_btn = ttk.Button(
            bootstrap_frame,
            text="完成验证",
            command=self._finish_bootstrap,
            state=tk.DISABLED,
        )
        self.finish_bootstrap_btn.pack(side=tk.LEFT, padx=(12, 0))

        download_frame = ttk.LabelFrame(container, text="下载", padding=12)
        download_frame.pack(fill=tk.X, pady=(12, 0))

        self.manga_var = tk.StringVar(value="")
        self.chapter_mode_var = tk.StringVar(value="单章")
        self.chapter_input_var = tk.StringVar(value="1")
        self.headless_var = tk.BooleanVar(value=False)
        self.http_mode_var = tk.BooleanVar(value=False)

        self._add_row(download_frame, 0, "漫画名/URL", self.manga_var)

        ttk.Label(download_frame, text="章节模式", width=12).grid(
            row=1, column=0, sticky="w", pady=2
        )
        mode = ttk.Combobox(
            download_frame,
            textvariable=self.chapter_mode_var,
            values=["单章", "范围", "全部"],
            state="readonly",
            width=12,
        )
        mode.grid(row=1, column=1, sticky="w", pady=2)

        self._add_row(download_frame, 2, "章节输入", self.chapter_input_var)

        hint = ttk.Label(
            download_frame,
            text="单章输入章节号(如 1/28)或 chapter-28，范围示例 1-5，全部可留空",
        )
        hint.grid(row=3, column=1, sticky="w", pady=(2, 8))

        flags_row = ttk.Frame(download_frame)
        flags_row.grid(row=4, column=1, sticky="w")
        ttk.Checkbutton(
            flags_row,
            text="不打开浏览器(无头)",
            variable=self.headless_var,
        ).pack(side=tk.LEFT, padx=(0, 12))
        ttk.Checkbutton(
            flags_row,
            text="无浏览器(HTTP模式)",
            variable=self.http_mode_var,
        ).pack(side=tk.LEFT, padx=(0, 12))

        self.download_btn = ttk.Button(
            flags_row, text="开始下载", command=self._start_download
        )
        self.download_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(
            flags_row, text="停止", command=self._stop_download, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(12, 0))

        log_frame = ttk.LabelFrame(container, text="日志", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

        self.log_text = tk.Text(log_frame, height=12, wrap=tk.WORD)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=scrollbar.set)

        self._log("提示：首次使用请先执行 Bootstrap。")

    def _add_row(
        self, parent: tk.Widget, row: int, label: str, variable: tk.StringVar
    ) -> None:
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky="w")
        entry = ttk.Entry(parent, textvariable=variable, width=50)
        entry.grid(row=row, column=1, sticky="w", pady=2)

    def _log(self, message: str) -> None:
        def append() -> None:
            self.log_text.insert(tk.END, message + "\n")
            self.log_text.see(tk.END)

        self.root.after(0, append)

    def _set_busy(
        self, busy: bool, allow_finish: bool = False, allow_stop: bool = False
    ) -> None:
        state = tk.DISABLED if busy else tk.NORMAL
        self.bootstrap_btn.configure(state=state)
        self.download_btn.configure(state=state)
        if allow_finish:
            self.finish_bootstrap_btn.configure(state=tk.NORMAL)
        else:
            self.finish_bootstrap_btn.configure(state=tk.DISABLED)
        if allow_stop:
            self.stop_btn.configure(state=tk.NORMAL)
        else:
            self.stop_btn.configure(state=tk.DISABLED)

    def _start_bootstrap(self) -> None:
        self.bootstrap_event.clear()
        self._set_busy(True, allow_finish=True, allow_stop=False)

        manga_value = self.manga_var.get().strip()
        target_url = DEFAULT_BASE_URL
        base_url = DEFAULT_BASE_URL
        if manga_value:
            if manga_value.startswith("http://") or manga_value.startswith("https://"):
                target_url = manga_value
                base_url = _normalize_base_url(manga_value)
            else:
                slug = _slugify_keyword(manga_value) or manga_value
                target_url = _infer_url(DEFAULT_BASE_URL, slug, "manga")

        async def run() -> None:
            await self._bootstrap_state(
                base_url=base_url,
                storage_state=DEFAULT_STORAGE_STATE,
                user_data_dir=DEFAULT_PROFILE_DIR,
                channel=DEFAULT_CHANNEL,
                target_url=target_url,
            )

        self._run_async(run(), "状态保存完成", allow_finish=True)

    def _finish_bootstrap(self) -> None:
        self.bootstrap_event.set()

    def _stop_download(self) -> None:
        self.stop_event.set()
        self._log("正在停止下载...")
        if self.active_loop and self.active_task:
            self.active_loop.call_soon_threadsafe(self.active_task.cancel)

    def _start_download(self) -> None:
        self.stop_event.clear()
        self._set_busy(True, allow_finish=False, allow_stop=True)

        manga_value = self.manga_var.get().strip()
        chapter_mode = self.chapter_mode_var.get().strip()
        chapter_input_value = self.chapter_input_var.get().strip()
        headless = self.headless_var.get()
        http_mode = self.http_mode_var.get()
        if headless:
            self._log("无头模式可能触发 Cloudflare 拦截，若失败请取消无头模式。")
        if http_mode:
            self._log("HTTP 模式将完全不打开浏览器，但必须有有效状态文件。")

        async def run() -> None:
            if not manga_value:
                raise RuntimeError("请填写漫画名或 URL")
            if not Path(DEFAULT_STORAGE_STATE).exists():
                raise RuntimeError("未找到状态文件，请先执行 Bootstrap")

            base_url = DEFAULT_BASE_URL
            if manga_value.startswith("http://") or manga_value.startswith("https://"):
                base_url = _normalize_base_url(manga_value)
            user_agent = None
            if http_mode or headless:
                user_agent = DEFAULT_USER_AGENTS[0]
            config = ScraperConfig(
                base_url=base_url,
                headless=headless,
                storage_state_path=DEFAULT_STORAGE_STATE,
                browser_channel=DEFAULT_CHANNEL,
                user_data_dir=DEFAULT_PROFILE_DIR,
                challenge_wait_ms=DEFAULT_CHALLENGE_WAIT_MS,
                manual_challenge=False,
                http_mode=http_mode,
                override_user_agent=http_mode or headless,
                user_agent=user_agent,
            )
            downloader = AsyncDownloader(
                DownloadConfig(concurrency=DEFAULT_CONCURRENCY)
            )
            scraper = _select_scraper(base_url, config, downloader)
            engine = ScraperEngine(
                scraper, EngineConfig(output_root=Path(DEFAULT_OUTPUT_ROOT))
            )

            robots_path = "/manga/" if "mangaforfree.com" in base_url else "/webtoon/"
            await engine.advise_robots(robots_path)

            if manga_value.startswith("http://") or manga_value.startswith("https://"):
                manga_id = _infer_id(manga_value)
                manga_url = manga_value
            else:
                slug = _slugify_keyword(manga_value) or manga_value
                manga_id = slug
                manga_url = _infer_url(base_url, slug, "manga")
            manga = Manga(id=manga_id, title=manga_value or manga_id, url=manga_url)

            chapter_input = chapter_input_value
            chapters: list[Chapter]
            if chapter_mode == "全部":
                all_chapters = await engine.list_chapters(manga)
                if not all_chapters:
                    raise RuntimeError("未找到章节")
                chapters = list(all_chapters)
            elif chapter_mode == "范围":
                if not chapter_input:
                    raise RuntimeError("请填写章节范围")
                start, end = _parse_chapter_range(chapter_input)
                all_chapters = await engine.list_chapters(manga)
                if not all_chapters:
                    raise RuntimeError("未找到章节")
                chapters = _select_chapters_by_range(
                    list(all_chapters), float(start), float(end)
                )
            else:
                if not chapter_input:
                    chapter_input = "1"
                if (
                    chapter_input.startswith("http://")
                    or chapter_input.startswith("https://")
                    or "chapter-" in chapter_input
                ):
                    chapter_id = _infer_id(chapter_input)
                    chapter_url = _infer_url(
                        base_url, chapter_input, "chapter", manga_id=manga.id
                    )
                    chapters = [
                        Chapter(id=chapter_id, title=chapter_id, url=chapter_url)
                    ]
                else:
                    try:
                        number = float(chapter_input)
                    except ValueError as exc:
                        raise RuntimeError("单章模式请输入章节号或 chapter-xx") from exc
                    all_chapters = await engine.list_chapters(manga)
                    if not all_chapters:
                        raise RuntimeError("未找到章节")
                    matched = _find_chapter_by_number(list(all_chapters), number)
                    if not matched:
                        raise RuntimeError("未找到对应章节号")
                    chapters = [matched]

            self._log(f"漫画: {manga.title}")
            self._log(f"章节: {[chapter.title for chapter in chapters]}")

            total_ok = 0
            total_failed = 0
            if not http_mode and not headless and len(chapters) > 1:
                async with scraper._browser_context() as context:
                    for chapter in chapters:
                        if self.stop_event.is_set():
                            self._log("已停止下载")
                            return
                        chapter_dir = safe_name(chapter.id or chapter.title)
                        manga_dir = safe_name(manga.title or manga.id)
                        output_root = (
                            Path(DEFAULT_OUTPUT_ROOT) / manga_dir / chapter_dir
                        )
                        report = await scraper.download_images_with_context(
                            context, manga, chapter, output_root
                        )
                        total_ok += report.success_count
                        total_failed += report.failed_count
                        self._log(
                            f"下载: {chapter.title} 成功={report.success_count} 失败={report.failed_count}"
                        )
                        self._log(f"清单: {report.manifest_path}")
            else:
                for chapter in chapters:
                    if self.stop_event.is_set():
                        self._log("已停止下载")
                        return
                    try:
                        report = await engine.download_chapter(manga, chapter)
                    except CloudflareChallengeError as exc:
                        if headless:
                            self._log("无头模式被 Cloudflare 拦截，请取消无头后重试。")
                        raise exc
                    total_ok += report.success_count
                    total_failed += report.failed_count
                    self._log(
                        f"下载: {chapter.title} 成功={report.success_count} 失败={report.failed_count}"
                    )
                    self._log(f"清单: {report.manifest_path}")

            self._log(f"总计成功: {total_ok} 总计失败: {total_failed}")

        self._run_async(run(), "下载完成", allow_stop=True)

    def _run_async(
        self,
        coro: Coroutine[Any, Any, None],
        done_message: str,
        allow_finish: bool = False,
        allow_stop: bool = False,
    ) -> None:
        def runner() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            task = loop.create_task(coro)
            self.active_loop = loop
            self.active_task = task
            try:
                loop.run_until_complete(task)
                self._log(done_message)
            except asyncio.CancelledError:
                self._log("下载已停止")
            except Exception as exc:  # noqa: BLE001
                self._log(f"错误: {exc}")
            finally:
                self.active_task = None
                self.active_loop = None
                loop.close()
                self.root.after(0, self._set_busy, False, False, False)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()

    async def _bootstrap_state(
        self,
        base_url: str,
        storage_state: str,
        user_data_dir: str,
        channel: str | None,
        target_url: str | None,
    ) -> None:
        from playwright.async_api import async_playwright

        data_dir = Path(user_data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        launch_options = {
            "headless": False,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if channel:
            launch_options["channel"] = channel

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(data_dir),
                **launch_options,
            )
            page = await context.new_page()
            await page.goto(target_url or base_url, wait_until="domcontentloaded")
            self._log("浏览器已打开，请完成验证后点击“完成验证”。")
            await asyncio.to_thread(self.bootstrap_event.wait)
            path = Path(storage_state)
            path.parent.mkdir(parents=True, exist_ok=True)
            await context.storage_state(path=str(path))
            await context.close()


def main() -> None:
    root = tk.Tk()
    ScraperGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
