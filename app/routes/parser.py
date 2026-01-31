from pathlib import Path
import logging
from urllib.parse import parse_qs, urlparse

import anyio
from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel

from app.deps import get_settings
from app.routes import scraper as scraper_routes
from app.routes.scraper import ScraperCatalogRequest
from core.parser.list_parser import list_parse
from core.parser.rule_parser import rule_parse
from core.parser.ai_refiner import ai_refine, FIELDS
from core.parser.utils import is_missing, merge_warnings

router = APIRouter(prefix="/parser", tags=["parser"])
logger = logging.getLogger("parser")


class ParseRequest(BaseModel):
    url: str
    mode: str = "http"


class ParseListRequest(BaseModel):
    url: str
    mode: str = "http"


class ParserListResponse(BaseModel):
    page_type: str
    recognized: bool
    site: str | None
    downloadable: bool
    items: list[dict[str, object]]
    warnings: list[str]


def fetch_html(url: str, mode: str = "http") -> str:
    if not url or not url.strip():
        raise HTTPException(status_code=400, detail="URL 不能为空")
    mode = (mode or "http").strip().lower()
    headers = {"User-Agent": "Mozilla/5.0"}
    if mode == "http":
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise HTTPException(status_code=400, detail=f"请求失败: {exc}")
        if response.status_code >= 400:
            raise HTTPException(
                status_code=400, detail=f"请求失败（{response.status_code}）"
            )
        return response.text
    if mode == "playwright":
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        browser = None
        context = None
        page = None
        status_code = 0
        content = ""
        with sync_playwright() as playwright:
            try:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(user_agent=headers["User-Agent"])
                page = context.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
                status_code = response.status if response else 0
                content = page.content()
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=400, detail=f"Playwright fetch failed: {exc}"
                ) from exc
            finally:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
        if status_code >= 400:
            raise HTTPException(status_code=400, detail=f"请求失败（{status_code}）")
        return content
    raise HTTPException(status_code=400, detail="不支持的抓取模式")


@router.post("/parse")
def parse_url(payload: ParseRequest):
    logger.info("fetch_start | url=%s mode=%s", payload.url, payload.mode)
    html = fetch_html(payload.url, mode=payload.mode)
    logger.info(
        "fetch_end | url=%s mode=%s size=%s", payload.url, payload.mode, len(html)
    )
    logger.info("rule_parse | url=%s html_size=%s", payload.url, len(html))
    result = rule_parse(html, payload.url)
    if _needs_ai_refine(result):
        snippet = _build_snippet(html)
        try:
            logger.info("ai_refine | url=%s snippet_size=%s", payload.url, len(snippet))
            result = ai_refine(result, snippet)
        except Exception as exc:  # noqa: BLE001
            warnings = merge_warnings(
                result.get("warnings"), [f"AI refine failed: {exc}"]
            )
            result["warnings"] = warnings
    return result


@router.post("/list", response_model=ParserListResponse)
async def parse_list(payload: ParseListRequest) -> ParserListResponse:
    logger.info("fetch_start | url=%s mode=%s", payload.url, payload.mode)
    html = await anyio.to_thread.run_sync(fetch_html, payload.url, payload.mode)
    logger.info(
        "fetch_end | url=%s mode=%s size=%s", payload.url, payload.mode, len(html)
    )
    base_url = _normalize_base_url(payload.url)
    fallback_items = list_parse(html, base_url)
    site, _ = _recognize_site(payload.url)
    recognized = site is not None
    items = fallback_items
    warnings: list[str] = []
    downloadable = False
    if recognized:
        catalog_items, catalog_warnings = await _list_recognized_catalog(
            payload, payload.url
        )
        if catalog_items:
            items = catalog_items
        if catalog_warnings:
            warnings = merge_warnings(
                warnings,
                catalog_warnings + ["Catalog fetch failed; using fallback parser"],
            )
    else:
        warnings = merge_warnings(warnings, ["Unsupported site; using fallback parser"])
    if recognized and items:
        downloadable = True
    return ParserListResponse(
        page_type="list",
        recognized=recognized,
        site=site,
        downloadable=downloadable,
        items=items,
        warnings=warnings,
    )


def _needs_ai_refine(parsed: dict) -> bool:
    if any(is_missing(parsed.get(field)) for field in FIELDS):
        return True
    confidence = parsed.get("confidence")
    if isinstance(confidence, dict):
        return any(
            confidence.get(field, 1.0) < 0.55 for field in FIELDS if field in confidence
        )
    return False


def _build_snippet(html: str) -> str:
    if not html:
        return ""
    return html[:4000]


def _normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/")


def _recognize_site(url: str) -> tuple[str | None, str | None]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    mapping = {
        "toongod.org": "toongod",
        "mangaforfree.com": "mangaforfree",
    }
    site = mapping.get(host)
    if not site:
        return None, None
    scheme = parsed.scheme or "https"
    return site, f"{scheme}://{host}"


def _parse_catalog_url(url: str) -> tuple[str, int, str | None]:
    parsed = urlparse(url)
    path = parsed.path or "/"
    segments = [segment for segment in path.split("/") if segment]
    page = 1
    if "page" in segments:
        page_index = segments.index("page")
        if page_index + 1 < len(segments):
            page_value = segments[page_index + 1]
            try:
                page = int(page_value)
            except ValueError:
                page = 1
            segments = segments[:page_index]
            path = "/" + "/".join(segments) + "/"
    query = parse_qs(parsed.query)
    orderby = query.get("m_orderby", [None])[0]
    return path if path.startswith("/") else f"/{path}", page, orderby


async def _list_recognized_catalog(
    payload: ParseListRequest, url: str
) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    site, base_url = _recognize_site(url)
    if not site or not base_url:
        return [], ["Unrecognized site"]
    path, page, orderby = _parse_catalog_url(url)
    config = ScraperCatalogRequest(
        base_url=base_url,
        http_mode=payload.mode == "http",
        headless=payload.mode != "http",
        manual_challenge=False,
        storage_state_path=None,
        user_data_dir=None,
        browser_channel=None,
        user_agent=None,
        concurrency=6,
        page=page,
        orderby=orderby,
        path=path,
    )
    settings = get_settings()
    data_root = Path(settings.data_dir)
    try:
        engine, _ = scraper_routes._build_engine(config, data_root)
        result = await engine.list_catalog(config.page, config.orderby, config.path)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Catalog fetch failed: {exc}")
        return [], warnings
    items = []
    for item in result.items:
        items.append(
            {
                "id": item.id,
                "title": item.title,
                "url": item.url,
                "cover_url": item.cover_url,
            }
        )
    return items, warnings
