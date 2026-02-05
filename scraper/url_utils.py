from __future__ import annotations

import re
from urllib.parse import urlparse


def infer_id(value: str) -> str:
    if value.startswith("http://") or value.startswith("https://"):
        path = urlparse(value).path.rstrip("/")
        return path.split("/")[-1]
    return value


def infer_url(
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


def normalize_base_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/")


def slugify_keyword(keyword: str) -> str:
    value = keyword.strip().lower().replace("_", " ")
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s\-]+", "-", value)
    return value.strip("-")


def parse_chapter_range(value: str) -> tuple[int, int]:
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
