from __future__ import annotations

import asyncio
import json
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Iterable

import aiohttp

from .base import Chapter, Manga, UserAgentPool
from .rate_limit import RequestRateLimiter


@dataclass(frozen=True)
class DownloadItem:
    index: int
    url: str
    filename: str | None = None
    referer: str | None = None


@dataclass
class DownloadConfig:
    concurrency: int = 6
    timeout_sec: int = 25
    max_retries: int = 4
    backoff_base: float = 0.6
    backoff_factor: float = 2.0
    backoff_max: float = 10.0
    queue_maxsize: int = 120
    rate_limit_rps: float = 2.0


@dataclass
class PageRecord:
    index: int
    url: str
    path: str
    ok: bool
    error: str | None = None


@dataclass
class DownloadReport:
    manga_id: str
    chapter_id: str
    output_dir: Path
    manifest_path: Path
    pages: list[PageRecord]

    @property
    def success_count(self) -> int:
        return sum(1 for page in self.pages if page.ok)

    @property
    def failed_count(self) -> int:
        return sum(1 for page in self.pages if not page.ok)


class TransientHttpError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"Transient HTTP status {status}")
        self.status = status


class AsyncDownloader:
    def __init__(
        self,
        config: DownloadConfig | None = None,
        user_agent_pool: UserAgentPool | None = None,
        request_limiter: RequestRateLimiter | None = None,
    ) -> None:
        self.config = config or DownloadConfig()
        self.user_agent_pool = user_agent_pool or UserAgentPool()
        self.request_limiter = request_limiter or RequestRateLimiter(
            self.config.rate_limit_rps
        )
        self.logger = logging.getLogger(__name__)

    async def download_all(
        self,
        items: Iterable[DownloadItem],
        manga: Manga,
        chapter: Chapter,
        output_dir: Path,
        manifest_path: Path,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> DownloadReport:
        async def producer(queue: asyncio.Queue[DownloadItem | object]) -> int:
            count = 0
            for item in items:
                await queue.put(item)
                count += 1
            return count

        return await self.download_with_producer(
            producer=producer,
            manga=manga,
            chapter=chapter,
            output_dir=output_dir,
            manifest_path=manifest_path,
            headers=headers,
            cookies=cookies,
        )

    async def download_with_producer(
        self,
        producer: Callable[[asyncio.Queue[DownloadItem | object]], Awaitable[int]],
        manga: Manga,
        chapter: Chapter,
        output_dir: Path,
        manifest_path: Path,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ) -> DownloadReport:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)

        queue: asyncio.Queue[DownloadItem | object] = asyncio.Queue(
            maxsize=self.config.queue_maxsize
        )
        semaphore = asyncio.Semaphore(self.config.concurrency)
        results: list[PageRecord] = []
        sentinel = object()

        timeout = aiohttp.ClientTimeout(total=self.config.timeout_sec)

        async with aiohttp.ClientSession(timeout=timeout, cookies=cookies) as session:
            workers = [
                asyncio.create_task(
                    self._worker(
                        queue,
                        sentinel,
                        session,
                        semaphore,
                        output_dir,
                        results,
                        headers,
                    )
                )
                for _ in range(self.config.concurrency)
            ]
            await producer(queue)
            for _ in workers:
                await queue.put(sentinel)
            await queue.join()
            await asyncio.gather(*workers)

        report = self._build_report(manga, chapter, output_dir, manifest_path, results)
        self._write_manifest(report)
        return report

    async def _worker(
        self,
        queue: asyncio.Queue[DownloadItem | object],
        sentinel: object,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        output_dir: Path,
        results: list[PageRecord],
        headers: dict[str, str] | None,
    ) -> None:
        while True:
            item = await queue.get()
            if item is sentinel:
                queue.task_done()
                break
            if not isinstance(item, DownloadItem):
                queue.task_done()
                continue
            record = await self._download_item(
                item, session, semaphore, output_dir, headers
            )
            results.append(record)
            queue.task_done()

    async def _download_item(
        self,
        item: DownloadItem,
        session: aiohttp.ClientSession,
        semaphore: asyncio.Semaphore,
        output_dir: Path,
        headers: dict[str, str] | None,
    ) -> PageRecord:
        async with semaphore:
            file_name = item.filename or f"{item.index}.jpg"
            file_path = output_dir / file_name
            try:
                if file_path.exists() and file_path.stat().st_size > 0:
                    return PageRecord(
                        index=item.index,
                        url=item.url,
                        path=str(file_path),
                        ok=True,
                    )
                data = await self._fetch_bytes(session, item.url, headers, item.referer)
                file_path.write_bytes(data)
                return PageRecord(
                    index=item.index, url=item.url, path=str(file_path), ok=True
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "download failed | url=%s error=%s",
                    item.url,
                    exc,
                )
                return PageRecord(
                    index=item.index,
                    url=item.url,
                    path=str(file_path),
                    ok=False,
                    error=str(exc),
                )

    async def _fetch_bytes(
        self,
        session: aiohttp.ClientSession,
        url: str,
        headers: dict[str, str] | None,
        referer: str | None,
    ) -> bytes:
        for attempt in range(self.config.max_retries + 1):
            request_headers = dict(headers or {})
            request_headers.setdefault("User-Agent", self.user_agent_pool.pick())
            if referer:
                request_headers["Referer"] = referer
            try:
                await self.request_limiter.acquire()
                async with session.get(url, headers=request_headers) as response:
                    if response.status in {403, 429}:
                        raise TransientHttpError(response.status)
                    response.raise_for_status()
                    return await response.read()
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                TransientHttpError,
            ) as exc:
                if attempt >= self.config.max_retries:
                    raise exc
                await asyncio.sleep(self._compute_backoff(attempt))
        raise RuntimeError("Exhausted retries")

    def _compute_backoff(self, attempt: int) -> float:
        base = self.config.backoff_base * (self.config.backoff_factor**attempt)
        delay = min(self.config.backoff_max, base)
        jitter = random.uniform(0, delay * 0.2)
        return delay + jitter

    def _build_report(
        self,
        manga: Manga,
        chapter: Chapter,
        output_dir: Path,
        manifest_path: Path,
        results: list[PageRecord],
    ) -> DownloadReport:
        ordered = sorted(results, key=lambda record: record.index)
        return DownloadReport(
            manga_id=manga.id,
            chapter_id=chapter.id,
            output_dir=output_dir,
            manifest_path=manifest_path,
            pages=ordered,
        )

    def _write_manifest(self, report: DownloadReport) -> None:
        payload = {
            "manga_id": report.manga_id,
            "chapter_id": report.chapter_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "pages": [
                {
                    "index": page.index,
                    "url": page.url,
                    "path": page.path,
                    "ok": page.ok,
                    "error": page.error,
                }
                for page in report.pages
            ],
        }
        report.manifest_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2)
        )
