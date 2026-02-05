"""爬虫模块 CLI 入口。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Sequence

import click

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import Chapter, EngineConfig, Manga, ScraperConfig, ScraperEngine
from scraper.downloader import AsyncDownloader, DownloadConfig
from scraper.implementations import MangaForFreeScraper, ToonGodScraper
from scraper.challenge import looks_like_challenge
from scraper.url_utils import infer_id as _infer_id
from scraper.url_utils import infer_url as _infer_url
from scraper.url_utils import normalize_base_url as _normalize_base_url
from scraper.url_utils import parse_chapter_range as _parse_chapter_range


DEFAULT_BASE_URL = "https://toongod.org"
DEFAULT_OUTPUT_ROOT = "data/raw"
DEFAULT_STORAGE_STATE = "data/toongod_state.json"
DEFAULT_PROFILE_DIR = "data/playwright_profile"


def _load_cookies(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("cookies 必须是 JSON 对象")
    return {str(key): str(value) for key, value in payload.items()}


def _preview_items(label: str, items: list[str], limit: int = 10) -> None:
    click.echo(f"{label}（共 {len(items)} 个）:")
    for idx, item in enumerate(items[:limit], start=1):
        click.echo(f"  {idx}. {item}")
    if len(items) > limit:
        click.echo(f"  ... 还有 {len(items) - limit} 个")


async def _wait_for_challenge_clear(page, timeout_ms: int) -> None:
    poll_ms = 1000
    deadline = time.monotonic() + (timeout_ms / 1000)
    warned = False
    while True:
        try:
            html = await page.content()
        except Exception:  # noqa: BLE001
            if time.monotonic() >= deadline:
                raise RuntimeError("验证未完成，请增加等待时间或稍后重试")
            await page.wait_for_timeout(poll_ms)
            continue
        if not looks_like_challenge(html):
            return
        if not warned:
            click.echo("检测到 Cloudflare 验证页，等待完成...")
            warned = True
        if time.monotonic() >= deadline:
            raise RuntimeError("验证未完成，请增加等待时间或稍后重试")
        await page.wait_for_timeout(poll_ms)


async def _bootstrap_state(
    base_url: str,
    storage_state: str,
    user_data_dir: str,
    channel: str | None,
    target_url: str | None,
    challenge_wait_ms: int,
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
        await _wait_for_challenge_clear(page, challenge_wait_ms)
        path = Path(storage_state)
        path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(path))
        await context.close()


def _build_engine(
    base_url: str,
    output_root: str,
    storage_state: str | None,
    channel: str | None,
    user_data_dir: str | None,
    use_profile: bool,
    cookies_path: str | None,
    concurrency: int,
    challenge_wait_ms: int,
    manual_challenge: bool,
    no_ua_override: bool,
    user_agent: str | None,
    http_mode: bool,
) -> ScraperEngine:
    base_url = _normalize_base_url(base_url)
    cookies = _load_cookies(cookies_path)
    config = ScraperConfig(
        base_url=base_url,
        headless=False,
        cookies=cookies,
        storage_state_path=storage_state,
        browser_channel=channel,
        user_data_dir=user_data_dir if use_profile else None,
        challenge_wait_ms=challenge_wait_ms,
        manual_challenge=manual_challenge,
        override_user_agent=not no_ua_override,
        user_agent=user_agent,
        http_mode=http_mode,
    )
    downloader = AsyncDownloader(DownloadConfig(concurrency=concurrency))
    if "mangaforfree.com" in base_url:
        scraper = MangaForFreeScraper(config, downloader=downloader)
    else:
        scraper = ToonGodScraper(config, downloader=downloader)
    return ScraperEngine(scraper, EngineConfig(output_root=Path(output_root)))


async def _download_chapters(
    engine: ScraperEngine,
    manga: Manga,
    chapters: Sequence[Chapter],
) -> None:
    click.echo(f"漫画: {manga.title}")
    click.echo(f"章节: {[chapter.title for chapter in chapters]}")
    total_ok = 0
    total_failed = 0
    for chapter in chapters:
        report = await engine.download_chapter(manga, chapter)
        total_ok += report.success_count
        total_failed += report.failed_count
        click.echo(
            f"下载: {chapter.title} 成功={report.success_count} 失败={report.failed_count}"
        )
        click.echo(f"清单: {report.manifest_path}")
    click.echo(f"总计成功: {total_ok} 总计失败: {total_failed}")


@click.group()
def cli() -> None:
    """爬虫 CLI 入口。"""


@cli.command()
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True)
@click.option("--storage-state", default=DEFAULT_STORAGE_STATE, show_default=True)
@click.option("--bootstrap-url", default=None)
@click.option("--channel", default="chrome", show_default=True)
@click.option("--user-data-dir", default=DEFAULT_PROFILE_DIR, show_default=True)
@click.option("--challenge-wait-ms", default=120000, show_default=True)
def bootstrap(
    base_url: str,
    storage_state: str,
    bootstrap_url: str | None,
    channel: str | None,
    user_data_dir: str,
    challenge_wait_ms: int,
) -> None:
    """执行 Cloudflare 初始化并保存状态。"""
    asyncio.run(
        _bootstrap_state(
            base_url=base_url,
            storage_state=storage_state,
            user_data_dir=user_data_dir,
            channel=channel,
            target_url=bootstrap_url,
            challenge_wait_ms=challenge_wait_ms,
        )
    )
    click.echo(f"状态已保存: {storage_state}")


@cli.command()
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True)
@click.option("--output-root", default=DEFAULT_OUTPUT_ROOT, show_default=True)
@click.option("--storage-state", default=DEFAULT_STORAGE_STATE, show_default=True)
@click.option("--channel", default="chrome", show_default=True)
@click.option("--user-data-dir", default=DEFAULT_PROFILE_DIR, show_default=True)
@click.option("--use-profile", is_flag=True)
@click.option("--cookies", default=None)
@click.option("--concurrency", default=6, show_default=True)
@click.option("--challenge-wait-ms", default=60000, show_default=True)
@click.option("--manual-challenge", is_flag=True)
@click.option("--no-ua-override", is_flag=True)
@click.option("--user-agent", default=None)
@click.option("--http-mode", is_flag=True, help="使用 HTTP 模式(不打开浏览器)")
@click.option("--keyword", default=None)
@click.option("--manga", default=None)
@click.option("--manga-index", default=0, show_default=True)
@click.option("--chapter", default=None)
@click.option("--chapter-index", default=0, show_default=True)
@click.option("--chapter-range", default=None)
@click.option("--all", "download_all", is_flag=True)
def download(
    base_url: str,
    output_root: str,
    storage_state: str | None,
    channel: str | None,
    user_data_dir: str,
    use_profile: bool,
    cookies: str | None,
    concurrency: int,
    challenge_wait_ms: int,
    manual_challenge: bool,
    no_ua_override: bool,
    user_agent: str | None,
    http_mode: bool,
    keyword: str | None,
    manga: str | None,
    manga_index: int,
    chapter: str | None,
    chapter_index: int,
    chapter_range: str | None,
    download_all: bool,
) -> None:
    """按参数下载指定章节。"""
    if storage_state and not Path(storage_state).exists():
        raise SystemExit("未找到状态文件，请先运行 bootstrap")

    base_url = _normalize_base_url(base_url)
    if manga and (manga.startswith("http://") or manga.startswith("https://")):
        base_url = _normalize_base_url(manga)
    if chapter and (chapter.startswith("http://") or chapter.startswith("https://")):
        base_url = _normalize_base_url(chapter)

    engine = _build_engine(
        base_url=base_url,
        output_root=output_root,
        storage_state=storage_state,
        channel=channel,
        user_data_dir=user_data_dir,
        use_profile=use_profile,
        cookies_path=cookies,
        concurrency=concurrency,
        challenge_wait_ms=challenge_wait_ms,
        manual_challenge=manual_challenge,
        no_ua_override=no_ua_override,
        user_agent=user_agent,
        http_mode=http_mode,
    )

    async def run() -> None:
        if manga:
            manga_id = _infer_id(manga)
            manga_url = _infer_url(base_url, manga, "manga")
            target_manga = Manga(id=manga_id, title=manga_id, url=manga_url)
        else:
            if not keyword:
                raise SystemExit("必须提供 keyword 或 manga")
            results = await engine.search(keyword)
            if not results:
                raise SystemExit("未找到漫画结果")
            if manga_index >= len(results):
                raise SystemExit("manga_index 超出范围")
            target_manga = results[manga_index]

        if chapter:
            chapter_id = _infer_id(chapter)
            chapter_url = _infer_url(
                base_url, chapter, "chapter", manga_id=target_manga.id
            )
            chapters = [Chapter(id=chapter_id, title=chapter_id, url=chapter_url)]
        else:
            all_chapters = await engine.list_chapters(target_manga)
            if not all_chapters:
                raise SystemExit("未找到章节")
            if download_all:
                chapters = all_chapters
            elif chapter_range:
                start, end = _parse_chapter_range(chapter_range)
                if end > len(all_chapters):
                    raise SystemExit("章节范围超出列表")
                chapters = all_chapters[start - 1 : end]
            else:
                if chapter_index >= len(all_chapters):
                    raise SystemExit("章节序号超出范围")
                chapters = [all_chapters[chapter_index]]

        await _download_chapters(engine, target_manga, chapters)

    asyncio.run(run())


@cli.command()
@click.option("--base-url", default=DEFAULT_BASE_URL, show_default=True)
@click.option("--output-root", default=DEFAULT_OUTPUT_ROOT, show_default=True)
@click.option("--storage-state", default=DEFAULT_STORAGE_STATE, show_default=True)
@click.option("--channel", default="chrome", show_default=True)
@click.option("--user-data-dir", default=DEFAULT_PROFILE_DIR, show_default=True)
@click.option("--use-profile", is_flag=True)
@click.option("--cookies", default=None)
@click.option("--concurrency", default=6, show_default=True)
@click.option("--challenge-wait-ms", default=60000, show_default=True)
@click.option("--manual-challenge", is_flag=True)
@click.option("--no-ua-override", is_flag=True)
@click.option("--user-agent", default=None)
@click.option("--http-mode", is_flag=True, help="使用 HTTP 模式(不打开浏览器)")
def interactive(
    base_url: str,
    output_root: str,
    storage_state: str,
    channel: str | None,
    user_data_dir: str,
    use_profile: bool,
    cookies: str | None,
    concurrency: int,
    challenge_wait_ms: int,
    manual_challenge: bool,
    no_ua_override: bool,
    user_agent: str | None,
    http_mode: bool,
) -> None:
    """交互式爬虫工作流。"""
    base_url = _normalize_base_url(click.prompt("基础 URL", default=base_url))
    storage_state = click.prompt("状态文件路径", default=storage_state)
    if click.confirm("使用持久化浏览器配置？", default=True):
        use_profile = True
        user_data_dir = click.prompt("配置目录", default=user_data_dir)
    else:
        use_profile = False
    channel_value = click.prompt("浏览器通道（留空使用默认）", default=channel or "")
    channel = channel_value.strip() or None
    manual_challenge = click.confirm("允许手动通过 Cloudflare？", default=True)
    no_ua_override = click.confirm("保持浏览器默认 UA？", default=True)
    http_mode = click.confirm("使用 HTTP 模式(不打开浏览器)？", default=False)
    concurrency = click.prompt("下载并发数", default=concurrency, type=int)
    challenge_wait_ms = click.prompt(
        "挑战等待毫秒", default=challenge_wait_ms, type=int
    )

    if not Path(storage_state).exists():
        if click.confirm("状态文件不存在，立即 bootstrap？", default=True):
            bootstrap_url = click.prompt(
                "Bootstrap 地址", default=f"{base_url.rstrip('/')}/webtoon/"
            )
            asyncio.run(
                _bootstrap_state(
                    base_url=base_url,
                    storage_state=storage_state,
                    user_data_dir=user_data_dir,
                    channel=channel,
                    target_url=bootstrap_url,
                    challenge_wait_ms=challenge_wait_ms,
                )
            )
            click.echo(f"状态已保存: {storage_state}")
        else:
            raise SystemExit("需要状态文件")

    engine = _build_engine(
        base_url=base_url,
        output_root=output_root,
        storage_state=storage_state,
        channel=channel,
        user_data_dir=user_data_dir,
        use_profile=use_profile,
        cookies_path=cookies,
        concurrency=concurrency,
        challenge_wait_ms=challenge_wait_ms,
        manual_challenge=manual_challenge,
        no_ua_override=no_ua_override,
        user_agent=user_agent,
        http_mode=http_mode,
    )

    async def run() -> None:
        use_keyword = click.confirm("是否使用关键词搜索漫画？", default=False)
        if use_keyword:
            keyword = click.prompt("关键词")
            results = await engine.search(keyword)
            if not results:
                raise SystemExit("未找到漫画结果")
            preview = [item.title for item in results]
            _preview_items("搜索结果", preview)
            choice = click.prompt("选择漫画序号", default=1, type=int)
            if choice <= 0 or choice > len(results):
                raise SystemExit("漫画序号超出范围")
            target_manga = results[choice - 1]
        else:
            manga_value = click.prompt("漫画 ID 或 URL", default="teacher-yunji")
            manga_id = _infer_id(manga_value)
            manga_url = _infer_url(base_url, manga_value, "manga")
            target_manga = Manga(id=manga_id, title=manga_id, url=manga_url)

        mode = click.prompt(
            "章节模式 (single/range/all/direct)",
            default="single",
            type=click.Choice(
                ["single", "range", "all", "direct"], case_sensitive=False
            ),
        )

        if mode == "direct":
            chapter_value = click.prompt("章节 ID 或 URL")
            chapter_id = _infer_id(chapter_value)
            chapter_url = _infer_url(
                base_url, chapter_value, "chapter", manga_id=target_manga.id
            )
            chapters = [Chapter(id=chapter_id, title=chapter_id, url=chapter_url)]
        else:
            all_chapters = await engine.list_chapters(target_manga)
            if not all_chapters:
                raise SystemExit("未找到章节")
            chapter_titles = [chapter.title for chapter in all_chapters]
            _preview_items("章节列表", chapter_titles)
            if mode == "all":
                chapters = all_chapters
            elif mode == "range":
                value = click.prompt("章节范围 (1-10)")
                start, end = _parse_chapter_range(value)
                if end > len(all_chapters):
                    raise SystemExit("章节范围超出列表")
                chapters = all_chapters[start - 1 : end]
            else:
                index = click.prompt("章节序号", default=1, type=int)
                if index <= 0 or index > len(all_chapters):
                    raise SystemExit("章节序号超出范围")
                chapters = [all_chapters[index - 1]]

        await _download_chapters(engine, target_manga, chapters)

    asyncio.run(run())


if __name__ == "__main__":
    cli()
