from __future__ import annotations

from dataclasses import dataclass

import httpx

from .base import DEFAULT_USER_AGENTS


@dataclass(frozen=True)
class FetchError(Exception):
    message: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.message


def fetch_html(url: str, mode: str = "http") -> str:
    if not url or not url.strip():
        raise FetchError("URL 不能为空", status_code=400)
    mode = (mode or "http").strip().lower()
    headers = {"User-Agent": DEFAULT_USER_AGENTS[0]}
    if mode == "http":
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                response = client.get(url, headers=headers)
        except httpx.RequestError as exc:
            raise FetchError(f"请求失败: {exc}", status_code=400) from exc
        if response.status_code >= 400:
            raise FetchError(f"请求失败（{response.status_code}）", status_code=400)
        return response.text
    if mode == "playwright":
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise FetchError(str(exc), status_code=400) from exc
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
                raise FetchError(
                    f"Playwright fetch failed: {exc}", status_code=400
                ) from exc
            finally:
                if page is not None:
                    page.close()
                if context is not None:
                    context.close()
                if browser is not None:
                    browser.close()
        if status_code >= 400:
            raise FetchError(f"请求失败（{status_code}）", status_code=400)
        return content
    raise FetchError("不支持的抓取模式", status_code=400)
