from __future__ import annotations

import json
import re
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup


_ARTICLE_TYPES = {
    "Article",
    "NewsArticle",
    "BlogPosting",
    "Report",
    "CreativeWork",
}


def rule_parse(html: str, url: str) -> dict:
    soup = BeautifulSoup(html or "", "html.parser")
    json_ld_items = _collect_json_ld(soup)
    json_ld = _pick_json_ld(json_ld_items)

    title = _value_or_none(_extract_json_ld_title(json_ld))
    author = _value_or_none(_extract_json_ld_author(json_ld))
    date = _value_or_none(_extract_json_ld_date(json_ld))
    summary = _value_or_none(_extract_json_ld_summary(json_ld))
    cover = _value_or_none(_extract_json_ld_cover(json_ld))
    content_text, paragraphs = _extract_json_ld_body(json_ld)

    title = title or _value_or_none(
        _first_meta(
            soup,
            [
                ("property", "og:title"),
                ("name", "twitter:title"),
                ("name", "title"),
            ],
        )
    )
    if not title:
        title_tag = soup.find("title")
        if title_tag:
            title = _clean_text(title_tag.get_text())

    author = author or _value_or_none(
        _first_meta(
            soup,
            [
                ("name", "author"),
                ("property", "article:author"),
            ],
        )
    )

    date = date or _value_or_none(
        _first_meta(
            soup,
            [
                ("property", "article:published_time"),
                ("property", "article:modified_time"),
                ("name", "pubdate"),
                ("name", "date"),
                ("itemprop", "datePublished"),
            ],
        )
    )

    summary = summary or _value_or_none(
        _first_meta(
            soup,
            [
                ("name", "description"),
                ("property", "og:description"),
                ("name", "twitter:description"),
            ],
        )
    )

    cover = cover or _value_or_none(
        _first_meta(
            soup,
            [
                ("property", "og:image"),
                ("name", "twitter:image"),
                ("itemprop", "image"),
            ],
        )
    )

    if cover:
        cover = urljoin(url, cover)

    if not content_text or not paragraphs:
        content_text, paragraphs = _readability_fallback(soup)

    if not summary and paragraphs:
        summary = paragraphs[0]

    return {
        "title": title,
        "author": author,
        "date": date,
        "summary": summary,
        "cover": cover,
        "content_text": content_text,
        "paragraphs": paragraphs,
    }


def _collect_json_ld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in _normalize_json_ld(payload):
            if isinstance(item, dict):
                items.append(item)
    return items


def _normalize_json_ld(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from _normalize_json_ld(item)
        return
    if not isinstance(payload, dict):
        return
    graph = payload.get("@graph")
    if isinstance(graph, list):
        for item in graph:
            if isinstance(item, dict):
                yield item
        return
    yield payload


def _pick_json_ld(items: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    if not items:
        return None
    best_item = None
    best_score = -1
    for item in items:
        score = 0
        types = item.get("@type")
        type_list = [types] if isinstance(types, str) else types
        if isinstance(type_list, list):
            if any(t in _ARTICLE_TYPES for t in type_list if isinstance(t, str)):
                score += 3
        if item.get("articleBody"):
            score += 4
        if item.get("headline") or item.get("name"):
            score += 2
        if item.get("datePublished"):
            score += 1
        if item.get("description"):
            score += 1
        if score > best_score:
            best_score = score
            best_item = item
    return best_item


def _extract_json_ld_title(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    return item.get("headline") or item.get("name")


def _extract_json_ld_author(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    return _extract_author(item.get("author"))


def _extract_json_ld_date(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    return item.get("datePublished") or item.get("dateModified")


def _extract_json_ld_summary(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    return item.get("description")


def _extract_json_ld_cover(item: dict[str, Any] | None) -> str | None:
    if not item:
        return None
    return _extract_image(item.get("image"))


def _extract_json_ld_body(
    item: dict[str, Any] | None,
) -> tuple[str | None, list[str]]:
    if not item:
        return None, []
    body = item.get("articleBody")
    if not body or not isinstance(body, str):
        return None, []
    paragraphs = _split_paragraphs(body)
    content_text = "\n\n".join(paragraphs) if paragraphs else _clean_text(body)
    return content_text or None, paragraphs


def _extract_author(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        name = value.get("name") or value.get("givenName")
        if name:
            return str(name)
        return None
    if isinstance(value, list):
        names = []
        for item in value:
            name = _extract_author(item)
            if name:
                names.append(name)
        if names:
            return ", ".join(names)
    return None


def _extract_image(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        candidate = value.get("url") or value.get("@id")
        return str(candidate) if candidate else None
    if isinstance(value, list):
        for item in value:
            candidate = _extract_image(item)
            if candidate:
                return candidate
    return None


def _first_meta(soup: BeautifulSoup, lookups: list[tuple[str, str]]) -> str | None:
    for attr, key in lookups:
        tag = soup.find("meta", attrs={attr: key})
        if tag:
            content = tag.get("content")
            if content:
                return content.strip()
    return None


def _readability_fallback(soup: BeautifulSoup) -> tuple[str | None, list[str]]:
    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "header",
            "footer",
            "nav",
            "aside",
            "form",
            "iframe",
        ]
    ):
        tag.decompose()

    candidates = soup.find_all(["article", "main", "section", "div"])
    if not candidates and soup.body:
        candidates = [soup.body]
    best = None
    best_score = 0
    best_paragraphs: list[str] = []
    for candidate in candidates:
        paragraphs = _paragraphs_from_element(candidate)
        text = _clean_text(candidate.get_text(" ", strip=True))
        score = len(text) + 25 * len(paragraphs)
        if score > best_score:
            best_score = score
            best = candidate
            best_paragraphs = paragraphs

    if best is None:
        return None, []

    if not best_paragraphs:
        best_paragraphs = _split_paragraphs(best.get_text("\n", strip=True))
    content_text = "\n\n".join(best_paragraphs) if best_paragraphs else None
    return content_text, best_paragraphs


def _paragraphs_from_element(element: Any) -> list[str]:
    paragraphs = []
    for p in element.find_all("p"):
        text = _clean_text(p.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)
    return paragraphs


def _split_paragraphs(text: str) -> list[str]:
    if "<" in text and ">" in text:
        soup = BeautifulSoup(text, "html.parser")
        paragraphs = _paragraphs_from_element(soup)
        if paragraphs:
            return paragraphs
        text = soup.get_text("\n", strip=True)
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
    if chunks:
        return chunks
    return [line.strip() for line in text.splitlines() if line.strip()]


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _value_or_none(value: str | None) -> str | None:
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None
