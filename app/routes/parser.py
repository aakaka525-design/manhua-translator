import logging
from urllib.parse import parse_qs, urlparse

import anyio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import scraper.fetch as scraper_fetch

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
    try:
        return scraper_fetch.fetch_html(url, mode=mode)
    except scraper_fetch.FetchError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


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
    site, _ = _recognize_site(payload.url)
    recognized = site is not None
    items: list[dict[str, object]] = []
    warnings: list[str] = []
    downloadable = False
    if recognized:
        catalog_items, catalog_warnings = await _list_recognized_catalog(
            payload, payload.url
        )
        if catalog_items:
            items = catalog_items
        if catalog_warnings:
            warnings = merge_warnings(warnings, catalog_warnings)

    if not items:
        logger.info("fetch_start | url=%s mode=%s", payload.url, payload.mode)
        html = await anyio.to_thread.run_sync(fetch_html, payload.url, payload.mode)
        logger.info(
            "fetch_end | url=%s mode=%s size=%s", payload.url, payload.mode, len(html)
        )
        base_url = _normalize_base_url(payload.url)
        items = list_parse(html, base_url)
        if recognized:
            warnings = merge_warnings(
                warnings,
                ["Catalog fetch failed; using fallback parser"],
            )
        else:
            warnings = merge_warnings(
                warnings, ["Unsupported site; using fallback parser"]
            )
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
    try:
        settings = get_settings()
        catalog = await scraper_routes.list_catalog(config, settings=settings)
    except HTTPException as exc:
        warnings.append(f"Catalog fetch failed: {exc.detail}")
        return [], warnings
    items = [
        {
            "id": item.id,
            "title": item.title,
            "url": item.url,
            "cover_url": item.cover_url,
        }
        for item in catalog.items
    ]
    return items, warnings
