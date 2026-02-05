"""
Scraper API Routes.

Expose the crawler module to the frontend.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence, cast
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
    Query,
    Request,
)
from fastapi.responses import Response
import aiohttp
from pydantic import BaseModel

from scraper import Chapter, EngineConfig, Manga, ScraperConfig, ScraperEngine
from scraper.base import safe_name, normalize_url, load_storage_state_cookies
from scraper.downloader import AsyncDownloader, DownloadConfig
from scraper.implementations import MangaForFreeScraper, ToonGodScraper
from scraper.implementations.generic_playwright import CloudflareChallengeError
from scraper.url_utils import infer_id as _infer_id
from scraper.url_utils import infer_url as _infer_url

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


class ScraperStateInfoRequest(BaseModel):
    base_url: Optional[str] = None
    storage_state_path: Optional[str] = None


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


class ScraperStateInfoResponse(BaseModel):
    status: str
    cookie_name: Optional[str] = None
    expires_at: Optional[float] = None
    expires_at_text: Optional[str] = None
    expires_in_sec: Optional[int] = None
    message: Optional[str] = None


class ScraperAccessCheckRequest(BaseModel):
    base_url: str
    storage_state_path: Optional[str] = None
    path: Optional[str] = None


class ScraperAccessCheckResponse(BaseModel):
    status: str
    http_status: Optional[int] = None
    message: Optional[str] = None


class ScraperUploadResponse(BaseModel):
    path: str
    status: str
    message: Optional[str] = None
    expires_at: Optional[float] = None
    expires_at_text: Optional[str] = None


class ScraperImageResponse(BaseModel):
    status: str
    message: Optional[str] = None


class ScraperAuthUrlResponse(BaseModel):
    url: str


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


def _match_domain(cookie_domain: str, host: str) -> bool:
    if not cookie_domain or not host:
        return False
    domain = cookie_domain.lstrip(".").lower()
    host = host.lower()
    return host == domain or host.endswith(f".{domain}")


def _cookie_expires(cookie: dict) -> float | None:
    value = cookie.get("expires")
    if value is None:
        value = cookie.get("expiry")
    if value is None:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _build_cookie_header(storage_state_path: Optional[str], host: str) -> str:
    cookies = load_storage_state_cookies(storage_state_path, domain_filter=host or None)
    if not cookies:
        return ""
    return "; ".join(f"{name}={value}" for name, value in cookies.items())


def _default_state_path(base_url: str) -> Path:
    base_url = _normalize_base_url(base_url)
    name = (
        "mangaforfree_state.json"
        if "mangaforfree.com" in base_url
        else "toongod_state.json"
    )
    return Path("data") / name


def _cover_cache_path(url: str) -> Path:
    parsed = urlparse(url)
    ext = Path(parsed.path).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        ext = ".jpg"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return Path("data") / "cache" / "covers" / f"{digest}{ext}"


def _cover_cache_path_for_manga(base_url: str, manga_id: str, ext: str) -> Path:
    host = urlparse(base_url).hostname or "site"
    prefix = safe_name(host)
    safe_id = safe_name(manga_id)
    return Path("data") / "cache" / "covers" / f"{prefix}__{safe_id}{ext}"


async def _prefetch_cover_cache(
    items: Sequence[MangaPayload],
    base_url: str,
    storage_state_path: Optional[str],
    user_data_dir: Optional[str],
    browser_channel: Optional[str],
    user_agent: Optional[str],
    max_items: int = 24,
) -> None:
    if not items:
        return
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return
    targets = []
    for item in items:
        if not item.cover_url:
            continue
        if not _is_allowed_image_host(item.cover_url):
            continue
        cache_path = _cover_cache_path(item.cover_url)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            continue
        targets.append((item.cover_url, cache_path))
        if len(targets) >= max_items:
            break
    if not targets:
        return

    async with async_playwright() as playwright:
        context = None
        browser = None
        if user_data_dir:
            data_dir = Path(user_data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                str(data_dir),
                headless=True,
                channel=browser_channel,
                user_agent=user_agent or None,
            )
        else:
            browser = await playwright.chromium.launch(
                headless=True,
                channel=browser_channel,
            )
            storage_state = (
                storage_state_path
                if storage_state_path and Path(storage_state_path).exists()
                else None
            )
            context = await browser.new_context(
                storage_state=storage_state,
                user_agent=user_agent or None,
            )

        page = await context.new_page()
        for url, cache_path in targets:
            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    referer=base_url,
                    timeout=12000,
                )
                if not response or response.status >= 400:
                    continue
                data = await response.body()
            except Exception:
                continue
            if not data:
                continue
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)

            manga_id = None
            for item in items:
                if item.cover_url == url:
                    manga_id = item.id
                    break
            if manga_id:
                id_cache_path = _cover_cache_path_for_manga(
                    base_url, manga_id, cache_path.suffix
                )
                if not id_cache_path.exists():
                    id_cache_path.write_bytes(data)

        await context.close()
        if browser:
            await browser.close()


def _is_allowed_image_host(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.endswith("toongod.org") or host.endswith("mangaforfree.com")


async def _fetch_image_http(
    url: str, base_url: str, storage_state_path: Optional[str]
) -> tuple[bytes, str] | None:
    cookies = load_storage_state_cookies(
        storage_state_path,
        domain_filter=urlparse(base_url).hostname or None,
    )
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": base_url,
    }
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout, cookies=cookies) as session:
            async with session.get(url, headers=headers) as response:
                if response.status >= 400:
                    return None
                content_type = response.headers.get("content-type", "image/jpeg")
                data = await response.read()
                return data, content_type
    except Exception:
        return None


async def _fetch_image_playwright(
    url: str,
    base_url: str,
    storage_state_path: Optional[str],
    user_data_dir: Optional[str],
    browser_channel: Optional[str],
    user_agent: Optional[str],
) -> tuple[bytes, str] | None:
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    headers = {
        "User-Agent": user_agent or "Mozilla/5.0",
        "Referer": base_url,
    }
    async with async_playwright() as playwright:
        if user_data_dir:
            data_dir = Path(user_data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)
            context = await playwright.chromium.launch_persistent_context(
                str(data_dir),
                headless=True,
                channel=browser_channel,
                user_agent=user_agent or None,
            )
            response = await context.request.get(url, headers=headers)
            if response.status >= 400:
                await context.close()
                return None
            content_type = response.headers.get("content-type", "image/jpeg")
            data = await response.body()
            await context.close()
            return data, content_type

        browser = await playwright.chromium.launch(
            headless=True,
            channel=browser_channel,
        )
        storage_state = (
            storage_state_path
            if storage_state_path and Path(storage_state_path).exists()
            else None
        )
        context = await browser.new_context(
            storage_state=storage_state,
            user_agent=user_agent or None,
        )
        response = await context.request.get(url, headers=headers)
        if response.status >= 400:
            await context.close()
            await browser.close()
            return None
        content_type = response.headers.get("content-type", "image/jpeg")
        data = await response.body()
        await context.close()
        await browser.close()
        return data, content_type
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


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
        storage_state_path = None
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
        result = await engine.list_catalog(
            page=page, orderby=request.orderby, path=catalog_path
        )
    except NotImplementedError:
        raise HTTPException(status_code=400, detail="站点不支持目录浏览")
    except CloudflareChallengeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    results_list, has_more = result
    results_list = list(results_list)
    items = [
        MangaPayload(
            id=item.id,
            title=item.title,
            url=item.url,
            cover_url=getattr(item, "cover_url", None),
        )
        for item in results_list
    ]
    if not request.http_mode:
        await _prefetch_cover_cache(
            items,
            base_url=request.base_url,
            storage_state_path=request.storage_state_path,
            user_data_dir=request.user_data_dir,
            browser_channel=request.browser_channel,
            user_agent=request.user_agent,
        )
    return ScraperCatalogResponse(page=page, has_more=has_more, items=items)


@router.post("/state-info", response_model=ScraperStateInfoResponse)
async def state_info(request: ScraperStateInfoRequest):
    storage_state_path = _ensure_storage_path(request.storage_state_path)
    if not storage_state_path:
        return ScraperStateInfoResponse(status="missing", message="未填写状态文件")
    file_path = Path(storage_state_path)
    if not file_path.exists():
        return ScraperStateInfoResponse(status="not_found", message="状态文件不存在")
    try:
        payload = json.loads(file_path.read_text())
    except (OSError, json.JSONDecodeError):
        return ScraperStateInfoResponse(status="invalid", message="状态文件无法解析")
    cookies = payload.get("cookies")
    if not isinstance(cookies, list) or not cookies:
        return ScraperStateInfoResponse(
            status="no_cookie", message="状态文件中没有 cookie"
        )
    host = urlparse(request.base_url or "").hostname or ""
    if host:
        domain_cookies = [
            cookie
            for cookie in cookies
            if _match_domain(str(cookie.get("domain", "")), host)
        ]
    else:
        domain_cookies = list(cookies)
    if not domain_cookies:
        return ScraperStateInfoResponse(
            status="no_domain", message="未找到匹配域名的 cookie"
        )
    selected = None
    for name in ("cf_clearance", "__cf_bm"):
        for cookie in domain_cookies:
            if cookie.get("name") == name:
                selected = cookie
                break
        if selected:
            break
    if not selected:
        selected = domain_cookies[0]
    expires = _cookie_expires(selected)
    cookie_name = str(selected.get("name")) if selected.get("name") else None
    if not expires or expires <= 0:
        return ScraperStateInfoResponse(
            status="session",
            cookie_name=cookie_name,
            message="Cookie 无过期时间（会话）",
        )
    now = time.time()
    expires_in = int(expires - now)
    expires_text = datetime.fromtimestamp(expires).strftime("%Y-%m-%d %H:%M:%S")
    status = "valid" if expires_in > 0 else "expired"
    message = "Cookie 有效" if expires_in > 0 else "Cookie 已过期"
    return ScraperStateInfoResponse(
        status=status,
        cookie_name=cookie_name,
        expires_at=expires,
        expires_at_text=expires_text,
        expires_in_sec=expires_in,
        message=message,
    )


@router.post("/access-check", response_model=ScraperAccessCheckResponse)
async def access_check(request: ScraperAccessCheckRequest):
    target_path = request.path or "/"
    base_url = _normalize_base_url(request.base_url)
    url = normalize_url(base_url, target_path)
    host = urlparse(base_url).hostname or ""
    headers = {"User-Agent": "Mozilla/5.0"}
    cookie_header = _build_cookie_header(request.storage_state_path, host)
    if cookie_header:
        headers["Cookie"] = cookie_header
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as response:
                status_code = response.status
                if status_code == 403:
                    return ScraperAccessCheckResponse(
                        status="forbidden",
                        http_status=status_code,
                        message="访问被拒绝（403）",
                    )
                if status_code >= 400:
                    return ScraperAccessCheckResponse(
                        status="error",
                        http_status=status_code,
                        message=f"请求失败（{status_code}）",
                    )
                return ScraperAccessCheckResponse(
                    status="ok",
                    http_status=status_code,
                    message="可以访问",
                )
    except Exception as exc:  # noqa: BLE001
        return ScraperAccessCheckResponse(
            status="error",
            message=str(exc),
        )


@router.post("/upload-state", response_model=ScraperUploadResponse)
async def upload_state(
    base_url: str = Form(...),
    file: UploadFile = File(...),
):
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="仅支持 JSON 状态文件")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大")
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON 解析失败")
    cookies = payload.get("cookies") if isinstance(payload, dict) else None
    if not isinstance(cookies, list) or not cookies:
        raise HTTPException(status_code=400, detail="状态文件中没有 cookie")

    target_path = _default_state_path(base_url)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    info = await state_info(
        ScraperStateInfoRequest(
            base_url=base_url,
            storage_state_path=str(target_path),
        )
    )
    return ScraperUploadResponse(
        path=str(target_path),
        status=info.status,
        message=info.message,
        expires_at=info.expires_at,
        expires_at_text=info.expires_at_text,
    )


@router.get("/image")
async def proxy_image(
    url: str = Query(...),
    base_url: str = Query(...),
    storage_state_path: Optional[str] = Query(None),
    user_data_dir: Optional[str] = Query(None),
    browser_channel: Optional[str] = Query(None),
    user_agent: Optional[str] = Query(None),
):
    if not _is_allowed_image_host(url):
        raise HTTPException(status_code=400, detail="不支持的图片来源")
    storage_path = storage_state_path or str(_default_state_path(base_url))
    cache_path = _cover_cache_path(url)
    if cache_path.exists() and cache_path.stat().st_size > 0:
        content_type = mimetypes.guess_type(str(cache_path))[0] or "image/jpeg"
        return Response(content=cache_path.read_bytes(), media_type=content_type)

    data = await _fetch_image_http(url, base_url, storage_path)
    if data is None:
        data = await _fetch_image_playwright(
            url,
            base_url,
            storage_path,
            user_data_dir,
            browser_channel,
            user_agent,
        )
    if data is None:
        raise HTTPException(status_code=403, detail="图片获取失败")

    content, content_type = data
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(content)
    return Response(content=content, media_type=content_type)


@router.get("/auth-url", response_model=ScraperAuthUrlResponse)
async def get_auth_url(request: Request, settings=Depends(get_settings)):
    if settings.scraper_auth_url:
        return ScraperAuthUrlResponse(url=settings.scraper_auth_url)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("x-forwarded-host", request.headers.get("host", ""))
    if not host:
        host = request.url.netloc
    return ScraperAuthUrlResponse(url=f"{scheme}://{host}/auth")


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
