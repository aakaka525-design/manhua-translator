"""
Manga Management Routes.

Provides endpoints for browsing manga, chapters, and files.
"""

import os
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from ..deps import get_settings
from scraper.base import safe_name

router = APIRouter(prefix="/manga", tags=["manga"])


class ChapterInfo(BaseModel):
    id: str
    name: str
    has_original: bool
    has_translated: bool
    translated_count: int = 0
    page_count: int
    is_complete: bool = False


class MangaInfo(BaseModel):
    id: str
    name: str
    cover_url: Optional[str] = None
    chapter_count: int


def _resolve_manga_path(data_dir: Path, manga_id: str) -> Path:
    direct_path = data_dir / manga_id
    if direct_path.exists():
        return direct_path
    raw_path = data_dir / "raw" / manga_id
    if raw_path.exists():
        return raw_path
    return direct_path


@router.get("", response_model=List[MangaInfo])
async def list_manga(settings=Depends(get_settings)):
    """List all available manga in the data directory recursively."""
    data_dir = Path(settings.data_dir)
    if not data_dir.exists():
        return []

    mangas = []
    # Find directories that look like manga (contain subdirectories which are chapters)
    # A directory is a 'manga' if it has at least one subdirectory that contains images
    for root, dirs, files in os.walk(data_dir, followlinks=True):
        root_path = Path(root)
        if root_path == data_dir and "cache" in dirs:
            dirs.remove("cache")
        if root_path == data_dir:
            continue

        # If this directory has subdirectories, check if they are chapters
        subdirs = [root_path / d for d in dirs if not d.startswith(".")]
        if not subdirs:
            continue

        # Check if any subdir contains images and pick a cover
        is_manga = False
        cover_url = None
        cache_dir = data_dir / "cache" / "covers"
        safe_id = safe_name(root_path.name)
        candidates = []
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            candidate = cache_dir / f"{safe_id}{ext}"
            if candidate.exists():
                candidates.append(candidate)
            candidates.extend(cache_dir.glob(f"*__{safe_id}{ext}"))
        if candidates:
            chosen = max(candidates, key=lambda p: p.stat().st_mtime)
            cover_url = f"/data/{chosen.relative_to(data_dir).as_posix()}"
        image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
        for s in sorted(subdirs, key=lambda p: p.name):
            images = [
                f
                for f in s.iterdir()
                if f.is_file() and f.suffix.lower() in image_extensions
            ]
            if not images:
                continue
            images.sort(key=lambda p: p.name)
            is_manga = True
            if cover_url is None:
                cover_path = images[0].relative_to(data_dir).as_posix()
                cover_url = f"/data/{cover_path}"
            break

        if is_manga:
            rel_path = root_path.relative_to(data_dir)
            mangas.append(
                MangaInfo(
                    id=str(rel_path),
                    name=root_path.name,
                    cover_url=cover_url,
                    chapter_count=len(subdirs),
                )
            )

    mangas.sort(key=lambda x: x.name)
    return mangas


@router.get("/{manga_id:path}/chapters", response_model=List[ChapterInfo])
async def list_chapters(manga_id: str, settings=Depends(get_settings)):
    """List all chapters for a specific manga."""
    data_dir = Path(settings.data_dir)
    manga_path = _resolve_manga_path(data_dir, manga_id)
    output_manga_path = Path(settings.output_dir) / manga_id

    if not manga_path.exists():
        raise HTTPException(status_code=404, detail="Manga not found")

    chapters = []
    for path in manga_path.iterdir():
        if path.is_dir() and not path.name.startswith("."):
            translated_path = output_manga_path / path.name

            # Count images
            image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
            pages = [p for p in path.iterdir() if p.suffix.lower() in image_extensions]

            if pages:
                # 检查翻译目录是否有图片（不只是目录存在）
                translated_images = []
                if translated_path.exists():
                    translated_images = [
                        p
                        for p in translated_path.iterdir()
                        if p.suffix.lower() in image_extensions
                    ]
                translated_count = len(translated_images)
                has_translated_images = translated_count > 0
                is_complete = translated_count == len(pages) and len(pages) > 0

                chapters.append(
                    ChapterInfo(
                        id=path.name,
                        name=path.name,
                        has_original=True,
                        has_translated=has_translated_images,
                        translated_count=translated_count,
                        page_count=len(pages),
                        is_complete=is_complete,
                    )
                )

    import re

    def natural_sort_key(chapter_info):
        """Standard natural sort: splits string into numeric and non-numeric chunks"""
        return [
            int(text) if text.isdigit() else text.lower()
            for text in re.split(r"(\d+)", chapter_info.name)
        ]

    chapters.sort(key=natural_sort_key)
    return chapters


@router.get("/{manga_id:path}/chapter/{chapter_id}")
async def get_chapter_details(
    manga_id: str, chapter_id: str, settings=Depends(get_settings)
):
    """Get pages for a specific chapter, including original and translated paths."""
    data_dir = Path(settings.data_dir)
    manga_path = _resolve_manga_path(data_dir, manga_id) / chapter_id
    output_path = Path(settings.output_dir) / manga_id / chapter_id

    if not manga_path.exists():
        raise HTTPException(status_code=404, detail="Chapter not found")

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}
    pages = []

    # 自然数字排序函数
    import re

    def natural_sort_key(path):
        """按数字自然排序，如 1.jpg, 2.jpg, 10.jpg"""
        numbers = re.findall(r"\d+", path.stem)
        return int(numbers[0]) if numbers else 0

    # List original pages
    original_files = sorted(
        [p for p in manga_path.iterdir() if p.suffix.lower() in image_extensions],
        key=natural_sort_key,
    )

    from app.services.page_status import compute_page_status, find_translated_file

    report_dir = Path(settings.output_dir) / "quality_reports"
    low_quality_threshold = float(os.getenv("LOW_QUALITY_THRESHOLD", "0.7"))
    low_quality_ratio = float(os.getenv("LOW_QUALITY_RATIO", "0.3"))

    for p in original_files:
        translated_file = (
            find_translated_file(output_path, p.stem) if output_path.exists() else None
        )
        report_pattern = f"{manga_id}__{chapter_id}__{p.stem}__*.json"
        report_paths = list(report_dir.glob(report_pattern))
        status = compute_page_status(
            report_paths=report_paths,
            translated_exists=bool(translated_file and translated_file.exists()),
            low_quality_threshold=low_quality_threshold,
            low_quality_ratio=low_quality_ratio,
        )
        # Use manga_id which can be 'raw/Teacher_Yunji'
        pages.append(
            {
                "name": p.name,
                "original_url": f"/data/{manga_id}/{chapter_id}/{p.name}",
                "translated_url": (
                    f"/output/{manga_id}/{chapter_id}/{translated_file.name}"
                    if translated_file and translated_file.exists()
                    else None
                ),
                "status": status["status"],
                "status_reason": status["reason"],
                "warning_counts": status["warning_counts"],
            }
        )

    return {"manga_id": manga_id, "chapter_id": chapter_id, "pages": pages}


@router.delete("/{manga_id:path}/chapter/{chapter_id}")
async def delete_chapter(
    manga_id: str, chapter_id: str, settings=Depends(get_settings)
):
    """Delete a specific chapter (both original and translated)."""
    import shutil

    data_dir = Path(settings.data_dir)
    manga_path = _resolve_manga_path(data_dir, manga_id) / chapter_id
    output_path = Path(settings.output_dir) / manga_id / chapter_id

    deleted = False

    if manga_path.exists():
        shutil.rmtree(manga_path)
        deleted = True

    if output_path.exists():
        shutil.rmtree(output_path)
        deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail="Chapter not found")

    return {"message": f"Chapter {chapter_id} deleted"}


@router.delete("/{manga_id:path}")
async def delete_manga(manga_id: str, settings=Depends(get_settings)):
    """Delete a manga and all its chapters."""
    import shutil

    data_dir = Path(settings.data_dir)
    manga_path = _resolve_manga_path(data_dir, manga_id)
    output_manga_path = Path(settings.output_dir) / manga_id

    deleted = False

    if manga_path.exists():
        shutil.rmtree(manga_path)
        deleted = True

    if output_manga_path.exists():
        shutil.rmtree(output_manga_path)
        deleted = True

    if not deleted:
        raise HTTPException(status_code=404, detail="Manga not found")

    return {"message": f"Manga {manga_id} deleted"}
