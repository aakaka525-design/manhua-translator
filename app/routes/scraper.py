"""
Scraper API Routes.

Expose the crawler module to the frontend.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional, cast
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from scraper import Chapter, EngineConfig, Manga, ScraperConfig, ScraperEngine
from scraper.base import safe_name
from scraper.downloader import AsyncDownloader, DownloadConfig
from scraper.implementations import MangaForFreeScraper, ToonGodScraper
from scraper.implementations.generic_playwright import CloudflareChallengeError

from ..deps import get_settings


router = APIRouter(prefix="/scraper", tags=["scraper"])

_scraper_tasks: dict[str, dict[str, object]] = {}
_task_ttl_sec = 60 * 60


class MangaPayload(BaseModel):
    id: str
    title: Optional[str] = None
    url: Optional[str] = None
    cover_url: Optional[str] = None


class ChapterPayload(BaseModel):
    id: str
    title: Optional[str] = None
    url: Optional[str] = None
    index: Optional[int] = None
    downloaded: bool = False
    downloaded_count: int = 0
    downloaded_total: int = 0


class ScraperBaseRequest(BaseModel):
    base_url: str
    http_mode: bool = True
    headless: bool = True
    manual_challenge: bool = False
    storage_state_path: Optional[str] = None
    user_data_dir: Optional[str] = None
    browser_channel: Optional[str] = None
    cookies: Optional[dict[str, str]] = None
    concurrency: int = 6
    user_agent: Optional[str] = None


class ScraperSearchRequest(ScraperBaseRequest):
    keyword: str


class ScraperCatalogRequest(ScraperBaseRequest):
    page: int = 1
    orderby: Optional[str] = None
    path: Optional[str] = None


class ScraperChaptersRequest(ScraperBaseRequest):
    manga: MangaPayload


class ScraperDownloadRequest(ScraperBaseRequest):
    manga: MangaPayload
    chapter: ChapterPayload


class ScraperTaskStatus(BaseModel):
    task_id: str
    status: str
    message: Optional[str] = None
    report: Optional[dict[str, object]] = None


class ScraperCatalogResponse(BaseModel):
    page: int
    has_more: bool
    items: list[MangaPayload]


def _normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/")


def _normalize_catalog_path(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme and parsed.netloc:
        return parsed.path or "/"
    if not trimmed.startswith("/"):
        return f"/{trimmed}"
    return trimmed


def _infer_id(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        path = urlparse(value).path.rstrip("/")
        return path.split("/")[-1]
    return value


def _infer_url(
    base_url: str,
    value: str,
    kind: str,
    manga_id: str | None = None,
) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        return value
    path = "manga" if "mangaforfree.com" in base_url else "webtoon"
    if kind == "manga":
        return f"{base_url.rstrip('/')}/{path}/{value}"
    if kind == "chapter":
        if not manga_id:
            raise ValueError("chapter 需要 manga_id")
        return f"{base_url.rstrip('/')}/{path}/{manga_id}/{value}/"
    raise ValueError(f"unknown kind: {kind}")


def _coerce_concurrency(value: int) -> int:
    return max(1, min(value, 12))


def _ensure_storage_path(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    trimmed = path.strip()
    return trimmed or None


def _resolve_output_root(output_root: Path) -> Path:
    return output_root if output_root.name == "raw" else output_root / "raw"


def _read_manifest_counts(manifest_path: Path) -> tuple[int, int] | None:
    try:
        payload = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    pages = payload.get("pages")
    if not isinstance(pages, list):
        return None
    total = len(pages)
    success = sum(
        1 for page in pages if isinstance(page, dict) and page.get("ok") is True
    )
    return success, total


def _count_images(output_dir: Path) -> int:
    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    return sum(
        1
        for item in output_dir.iterdir()
        if item.is_file() and item.suffix.lower() in image_extensions
    )


def _get_download_stats(
    output_root: Path, manga: Manga, chapter: Chapter
) -> tuple[bool, int, int]:
    manga_dir = safe_name(manga.id or manga.title)
    chapter_dir = safe_name(chapter.id or chapter.title)
    output_dir = output_root / manga_dir / chapter_dir
    if not output_dir.exists():
        return False, 0, 0
    manifest_path = output_dir / "manifest.json"
    if manifest_path.exists():
        counts = _read_manifest_counts(manifest_path)
        if counts:
            success, total = counts
            return success > 0, success, total
    image_count = _count_images(output_dir)
    if image_count <= 0:
        return False, 0, 0
    return True, image_count, image_count


def _build_engine(
    request: ScraperBaseRequest, output_root: Path
) -> tuple[ScraperEngine, str]:
    base_url = _normalize_base_url(request.base_url)
    storage_state_path = _ensure_storage_path(request.storage_state_path)
    user_data_dir = _ensure_storage_path(request.user_data_dir)
    if storage_state_path and not Path(storage_state_path).exists():
        if request.http_mode:
            storage_state_path = None
        else:
            raise HTTPException(
                status_code=400, detail="状态文件不存在，请先 bootstrap"
            )
    output_root = _resolve_output_root(output_root)
    config = ScraperConfig(
        base_url=base_url,
        http_mode=request.http_mode,
        headless=request.headless,
        manual_challenge=request.manual_challenge,
        browser_channel=request.browser_channel,
        user_data_dir=user_data_dir,
        storage_state_path=storage_state_path,
        cookies=request.cookies,
        user_agent=request.user_agent,
    )
    downloader = AsyncDownloader(
        DownloadConfig(concurrency=_coerce_concurrency(request.concurrency))
    )
    if "mangaforfree.com" in base_url:
        scraper = MangaForFreeScraper(config, downloader=downloader)
    else:
        scraper = ToonGodScraper(config, downloader=downloader)
    engine = ScraperEngine(scraper, EngineConfig(output_root=output_root))
    return engine, base_url


def _resolve_manga(base_url: str, payload: MangaPayload) -> Manga:
    manga_id = payload.id or _infer_id(payload.url or "")
    manga_url = payload.url or _infer_url(base_url, manga_id, "manga")
    title = payload.title or manga_id
    return Manga(id=manga_id, title=title, url=manga_url)


def _resolve_chapter(base_url: str, manga: Manga, payload: ChapterPayload) -> Chapter:
    chapter_id = payload.id or _infer_id(payload.url or "")
    chapter_url = payload.url or _infer_url(
        base_url, chapter_id, "chapter", manga_id=manga.id
    )
    title = payload.title or chapter_id
    return Chapter(id=chapter_id, title=title, url=chapter_url, index=payload.index)


def _set_task(
    task_id: str, status: str, message: str | None = None, report: dict | None = None
) -> None:
    _scraper_tasks[task_id] = {
        "status": status,
        "message": message,
        "report": report,
        "updated_at": time.time(),
    }
    _prune_tasks()


def _prune_tasks() -> None:
    if not _scraper_tasks:
        return
    now = time.time()
    expired = []
    for task_id, payload in _scraper_tasks.items():
        updated_at = cast(float | str | None, payload.get("updated_at"))
        if isinstance(updated_at, (int, float)):
            timestamp = float(updated_at)
        elif isinstance(updated_at, str):
            try:
                timestamp = float(updated_at)
            except ValueError:
                timestamp = now
        else:
            timestamp = now
        if now - timestamp > _task_ttl_sec:
            expired.append(task_id)
    for task_id in expired:
        _scraper_tasks.pop(task_id, None)


@router.post("/search", response_model=list[MangaPayload])
async def search_manga(request: ScraperSearchRequest, settings=Depends(get_settings)):
    engine, _ = _build_engine(request, Path(settings.data_dir))
    try:
        results = await engine.search(request.keyword)
    except CloudflareChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return [
        MangaPayload(
            id=item.id,
            title=item.title,
            url=item.url,
            cover_url=getattr(item, "cover_url", None),
        )
        for item in results
    ]


@router.post("/catalog", response_model=ScraperCatalogResponse)
async def list_catalog(request: ScraperCatalogRequest, settings=Depends(get_settings)):
    engine, _ = _build_engine(request, Path(settings.data_dir))
    page = max(1, request.page)
    catalog_path = _normalize_catalog_path(request.path)
    try:
        results, has_more = await engine.list_catalog(
            page=page, orderby=request.orderby, path=catalog_path
        )
    except NotImplementedError:
        raise HTTPException(status_code=400, detail="站点不支持目录浏览")
    except CloudflareChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    items = [
        MangaPayload(
            id=item.id,
            title=item.title,
            url=item.url,
            cover_url=getattr(item, "cover_url", None),
        )
        for item in results
    ]
    return ScraperCatalogResponse(page=page, has_more=has_more, items=items)


@router.post("/chapters", response_model=list[ChapterPayload])
async def list_chapters(
    request: ScraperChaptersRequest, settings=Depends(get_settings)
):
    engine, base_url = _build_engine(request, Path(settings.data_dir))
    manga = _resolve_manga(base_url, request.manga)
    output_root = _resolve_output_root(Path(settings.data_dir))
    try:
        chapters = await engine.list_chapters(manga)
    except CloudflareChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    payloads = []
    for item in chapters:
        downloaded, downloaded_count, downloaded_total = _get_download_stats(
            output_root, manga, item
        )
        payloads.append(
            ChapterPayload(
                id=item.id,
                title=item.title,
                url=item.url,
                index=item.index,
                downloaded=downloaded,
                downloaded_count=downloaded_count,
                downloaded_total=downloaded_total,
            )
        )
    return payloads


@router.post("/download", response_model=ScraperTaskStatus)
async def download_chapter(
    request: ScraperDownloadRequest, settings=Depends(get_settings)
):
    engine, base_url = _build_engine(request, Path(settings.data_dir))
    manga = _resolve_manga(base_url, request.manga)
    chapter = _resolve_chapter(base_url, manga, request.chapter)
    task_id = str(uuid4())
    _set_task(task_id, "pending", message="已提交下载任务")

    async def _run_download() -> None:
        _set_task(task_id, "running", message=f"下载中: {chapter.title}")
        try:
            report = await engine.download_chapter(manga, chapter)
            success_count = report.success_count
            failed_count = report.failed_count
            if success_count == 0:
                status = "error"
                message = "下载失败（未成功获取图片）"
            elif failed_count > 0:
                status = "partial"
                message = f"下载完成（成功 {success_count} / 失败 {failed_count}）"
            else:
                status = "success"
                message = f"下载完成（成功 {success_count}）"
            _set_task(
                task_id,
                status,
                message=message,
                report={
                    "manga_id": report.manga_id,
                    "chapter_id": report.chapter_id,
                    "output_dir": str(report.output_dir),
                    "manifest_path": str(report.manifest_path),
                    "success_count": report.success_count,
                    "failed_count": report.failed_count,
                },
            )
        except CloudflareChallengeError as exc:
            _set_task(task_id, "error", message=str(exc))
        except Exception as exc:  # noqa: BLE001
            _set_task(task_id, "error", message=str(exc))

    asyncio.create_task(_run_download())
    return ScraperTaskStatus(
        task_id=task_id, status="pending", message="已提交下载任务"
    )


@router.get("/task/{task_id}", response_model=ScraperTaskStatus)
async def get_scraper_task(task_id: str):
    _prune_tasks()
    task = _scraper_tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    message = task.get("message")
    report = task.get("report")
    report_payload = report if isinstance(report, dict) else None
    return ScraperTaskStatus(
        task_id=task_id,
        status=str(task.get("status")),
        message=str(message) if message is not None else None,
        report=report_payload,
    )
