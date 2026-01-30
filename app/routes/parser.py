import logging

from fastapi import APIRouter, HTTPException
import httpx
from pydantic import BaseModel

from core.parser.rule_parser import rule_parse
from core.parser.ai_refiner import ai_refine, FIELDS
from core.parser.utils import is_missing, merge_warnings

router = APIRouter(prefix="/parser", tags=["parser"])
logger = logging.getLogger("parser")


class ParseRequest(BaseModel):
    url: str
    mode: str = "http"


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
