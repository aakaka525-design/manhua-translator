from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


def list_parse(html: str, base_url: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    anchors = soup.find_all("a", href=True)
    with_images: list[Any] = []
    without_images: list[Any] = []
    for anchor in anchors:
        if anchor.find("img"):
            with_images.append(anchor)
        else:
            without_images.append(anchor)

    for anchor in with_images + without_images:
        href = anchor.get("href")
        if not href:
            continue
        normalized_url = urljoin(base_url, href)
        if normalized_url in seen_urls:
            continue

        cover_url = None
        img = anchor.find("img")
        if img:
            src = img.get("src")
            if src:
                cover_url = urljoin(base_url, src)

        title = _clean_text(anchor.get_text(" ", strip=True))
        if not title and img:
            alt_text = img.get("alt")
            if alt_text:
                title = _clean_text(str(alt_text))

        item = {
            "id": _derive_id(normalized_url),
            "title": title or None,
            "url": normalized_url,
            "cover_url": cover_url,
        }
        items.append(item)
        seen_urls.add(normalized_url)

    return items


def _derive_id(url: str) -> str:
    parsed = urlparse(url)
    path = (parsed.path or "").rstrip("/")
    segment = path.split("/")[-1] if path else ""
    if segment:
        return segment
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _clean_text(value: str) -> str:
    return " ".join((value or "").split())
