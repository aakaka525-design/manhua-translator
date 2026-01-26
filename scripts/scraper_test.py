"""ToonGod 爬虫烟测脚本。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scraper import Chapter, EngineConfig, Manga, ScraperConfig, ScraperEngine
from scraper.downloader import AsyncDownloader, DownloadConfig
from scraper.implementations import ToonGodScraper


def _load_cookies(path: str | None) -> dict[str, str] | None:
    if not path:
        return None
    payload = json.loads(Path(path).read_text())
    if not isinstance(payload, dict):
        raise ValueError("cookies 必须是 JSON 对象")
    return {str(key): str(value) for key, value in payload.items()}


def _infer_id(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        path = urlparse(value).path.rstrip("/")
        return path.split("/")[-1]
    return value


def _infer_url(
    base_url: str, value: str, kind: str, manga_id: str | None = None
) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if kind == "manga":
        return f"{base_url.rstrip('/')}/webtoon/{value}"
    if kind == "chapter":
        if not manga_id:
            raise ValueError("chapter 需要 manga_id")
        return f"{base_url.rstrip('/')}/webtoon/{manga_id}/{value}/"
    raise ValueError(f"unknown kind: {kind}")


def _parse_chapter_range(value: str) -> tuple[int, int]:
    match = re.match(r"^\s*(\d+)\s*[-:]\s*(\d+)\s*$", value)
    if not match:
        raise ValueError("章节范围格式应为 1-10")
    start = int(match.group(1))
    end = int(match.group(2))
    if start <= 0 or end <= 0:
        raise ValueError("章节范围必须为正整数")
    if start > end:
        start, end = end, start
    return start, end


async def _bootstrap_state(
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
        await asyncio.to_thread(
            input,
            "请在打开的浏览器中完成 Cloudflare 验证，然后回车继续...",
        )
        path = Path(storage_state)
        path.parent.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(path))
        await context.close()


async def run(args: argparse.Namespace) -> None:
    if args.bootstrap:
        if not args.storage_state:
            raise SystemExit("bootstrap 需要 --storage-state")
        target_url = args.bootstrap_url
        if not target_url and args.manga and args.chapter:
            manga_id = _infer_id(args.manga)
            target_url = _infer_url(
                args.base_url, args.chapter, "chapter", manga_id=manga_id
            )
        elif not target_url and args.manga:
            target_url = _infer_url(args.base_url, args.manga, "manga")
        await _bootstrap_state(
            base_url=args.base_url,
            storage_state=args.storage_state,
            user_data_dir=args.user_data_dir,
            channel=args.channel,
            target_url=target_url,
        )
        print("状态已保存:", args.storage_state)
        return

    if args.storage_state and not Path(args.storage_state).exists():
        raise SystemExit("未找到状态文件，请先运行 --bootstrap")

    cookies = _load_cookies(args.cookies)
    config = ScraperConfig(
        base_url=args.base_url,
        headless=args.headless,
        cookies=cookies,
        storage_state_path=args.storage_state,
        browser_channel=args.channel,
        user_data_dir=args.user_data_dir if args.use_profile else None,
        challenge_wait_ms=args.challenge_wait_ms,
        manual_challenge=args.manual_challenge,
        override_user_agent=not args.no_ua_override,
    )
    downloader = AsyncDownloader(DownloadConfig(concurrency=args.concurrency))
    scraper = ToonGodScraper(config, downloader=downloader)
    engine = ScraperEngine(scraper, EngineConfig(output_root=Path(args.output_root)))

    await engine.advise_robots("/webtoon/")

    if args.manga:
        manga_id = _infer_id(args.manga)
        manga_url = _infer_url(args.base_url, args.manga, "manga")
        manga = Manga(id=manga_id, title=manga_id, url=manga_url)
    else:
        if not args.keyword:
            raise SystemExit("必须提供 keyword 或 manga")
        results = await engine.search(args.keyword)
        if not results:
            raise SystemExit("未找到漫画结果")
        if args.manga_index >= len(results):
            raise SystemExit("漫画序号超出范围")
        manga = results[args.manga_index]

    if args.chapter:
        chapter_id = _infer_id(args.chapter)
        chapter_url = _infer_url(
            args.base_url, args.chapter, "chapter", manga_id=manga.id
        )
        chapters = [Chapter(id=chapter_id, title=chapter_id, url=chapter_url)]
    else:
        all_chapters = await engine.list_chapters(manga)
        if not all_chapters:
            raise SystemExit("未找到章节")
        if args.all:
            chapters = all_chapters
        elif args.chapter_range:
            start, end = _parse_chapter_range(args.chapter_range)
            if end > len(all_chapters):
                raise SystemExit("章节范围超出列表")
            chapters = all_chapters[start - 1 : end]
        else:
            if args.chapter_index >= len(all_chapters):
                raise SystemExit("章节序号超出范围")
            chapters = [all_chapters[args.chapter_index]]

    print("漫画:", manga.title)
    print("章节:", [chapter.title for chapter in chapters])
    reports = []
    for chapter in chapters:
        report = await engine.download_chapter(manga, chapter)
        reports.append(report)
        print(
            "下载:",
            chapter.title,
            report.success_count,
            "失败:",
            report.failed_count,
        )
        print("清单:", report.manifest_path)
    total_ok = sum(report.success_count for report in reports)
    total_failed = sum(report.failed_count for report in reports)
    print("总计成功:", total_ok, "总计失败:", total_failed)


def main() -> None:
    parser = argparse.ArgumentParser(description="ToonGod 爬虫烟测")
    parser.add_argument("--base-url", default="https://www.toongod.org")
    parser.add_argument("--keyword", help="搜索关键词")
    parser.add_argument("--manga", help="漫画 ID 或完整 URL")
    parser.add_argument("--chapter", help="章节 ID 或完整 URL")
    parser.add_argument("--manga-index", type=int, default=0)
    parser.add_argument("--chapter-index", type=int, default=0)
    parser.add_argument("--chapter-range", help="章节序号范围，例如 1-10")
    parser.add_argument("--all", action="store_true", help="下载所有章节")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cookies", help="cookies JSON 路径")
    parser.add_argument("--storage-state", help="playwright 状态文件路径")
    parser.add_argument("--bootstrap", action="store_true", help="初始化状态文件")
    parser.add_argument("--bootstrap-url", help="bootstrap 打开的 URL")
    parser.add_argument("--channel", help="Playwright 浏览器通道，例如 chrome")
    parser.add_argument(
        "--user-data-dir",
        default="data/playwright_profile",
        help="持久化配置目录",
    )
    parser.add_argument(
        "--use-profile",
        action="store_true",
        help="抓取时使用持久化配置",
    )
    parser.add_argument(
        "--challenge-wait-ms",
        type=int,
        default=15000,
        help="Cloudflare 挑战最大等待时间",
    )
    parser.add_argument(
        "--manual-challenge",
        action="store_true",
        help="允许手动通过 Cloudflare",
    )
    parser.add_argument(
        "--no-ua-override",
        action="store_true",
        help="不覆盖浏览器 UA（建议配合 profile）",
    )
    parser.add_argument("--output-root", default="data/raw")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
