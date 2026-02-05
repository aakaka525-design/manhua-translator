"""
Translation API Routes.

Provides endpoints for image translation operations.
"""

from pathlib import Path
from typing import Dict, Set, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import json
import asyncio

from core.models import (
    TaskContext,
    TaskStatus,
    TaskStatusResponse,
    TranslateImageRequest,
    TranslateImageResponse,
)
from core.pipeline import Pipeline
from ..deps import get_pipeline, get_settings

router = APIRouter(prefix="/translate", tags=["translation"])

# In-memory task storage
_tasks: Dict[UUID, TaskContext] = {}

# SSE event listeners
_listeners: Set[asyncio.Queue] = set()


async def broadcast_event(data: dict):
    """Broadcast an event to all connected SSE clients."""
    if not _listeners:
        return

    event_str = f"data: {json.dumps(data)}\n\n"
    for queue in _listeners:
        await queue.put(event_str)


async def pipeline_status_callback(stage: str, status: TaskStatus, task_id: UUID):
    """Callback for pipeline progress updates."""
    await broadcast_event(
        {
            "type": "progress",
            "task_id": str(task_id),
            "stage": stage,
            "status": status.value,
        }
    )


@router.get("/events")
async def sse_events():
    """Server-Sent Events endpoint for real-time status updates."""
    queue = asyncio.Queue()
    _listeners.add(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield event
        except asyncio.CancelledError:
            _listeners.remove(queue)
            raise

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/image", response_model=TranslateImageResponse)
async def translate_image(
    request: TranslateImageRequest,
    pipeline: Pipeline = Depends(get_pipeline),
    settings=Depends(get_settings),
):
    """
    Translate a single image.
    """
    if not Path(request.image_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {request.image_path}",
        )

    source_lang = request.source_language or settings.source_language
    target_lang = request.target_language or settings.target_language

    context = TaskContext(
        image_path=request.image_path,
        source_language=source_lang,
        target_language=target_lang,
    )

    # Process through pipeline with callback
    result = await pipeline.process(context, status_callback=pipeline_status_callback)

    _tasks[result.task.task_id] = result.task
    return TranslateImageResponse(
        task_id=result.task.task_id,
        status=result.task.status,
        output_path=result.task.output_path,
        regions_count=len(result.task.regions),
    )


class ChapterTranslateRequest(BaseModel):
    manga_id: str
    chapter_id: str
    source_language: Optional[str] = None  # 默认从 settings 获取
    target_language: Optional[str] = None  # 默认从 settings 获取


@router.post("/chapter")
async def translate_chapter_endpoint(
    request: ChapterTranslateRequest,
    background_tasks: BackgroundTasks,
    pipeline: Pipeline = Depends(get_pipeline),
    settings=Depends(get_settings),
):
    """
    Start translation for an entire chapter in the background.
    """
    manga_path = Path(settings.data_dir) / request.manga_id / request.chapter_id
    if not manga_path.exists():
        raise HTTPException(status_code=404, detail="Chapter not found")

    image_extensions = {".jpg", ".jpeg", ".png", ".webp"}

    # 自然数字排序函数
    import re

    def natural_sort_key(path):
        """按数字自然排序，如 1.jpg, 2.jpg, 10.jpg"""
        numbers = re.findall(r"\d+", path.stem)
        return int(numbers[0]) if numbers else 0

    image_files = sorted(
        [p for p in manga_path.iterdir() if p.suffix.lower() in image_extensions],
        key=natural_sort_key,
    )

    if not image_files:
        raise HTTPException(status_code=404, detail="No images found in chapter")

    # Background processing function
    async def process_chapter():
        # 使用 request 中的语言，如果为 None 则从 settings 获取
        source_lang = request.source_language or settings.source_language
        target_lang = request.target_language or settings.target_language

        contexts = [
            TaskContext(
                image_path=str(img_path),
                source_language=source_lang,
                target_language=target_lang,
            )
            for img_path in image_files
        ]

        # Override output paths to be inside the output dir
        output_base = Path(settings.output_dir) / request.manga_id / request.chapter_id
        output_base.mkdir(parents=True, exist_ok=True)

        for ctx in contexts:
            img_name = Path(ctx.image_path).name
            ctx.output_path = str(output_base / img_name)
            _tasks[ctx.task_id] = ctx

        await broadcast_event(
            {
                "type": "chapter_start",
                "manga_id": request.manga_id,
                "chapter_id": request.chapter_id,
                "total_pages": len(contexts),
            }
        )

        results = await pipeline.process_batch(
            contexts, status_callback=pipeline_status_callback
        )

        success_count = sum(1 for r in results if r.success)
        total_count = len(contexts)
        saved_count = sum(
            1 for img_path in image_files if (output_base / img_path.name).exists()
        )

        await broadcast_event(
            {
                "type": "chapter_complete",
                "manga_id": request.manga_id,
                "chapter_id": request.chapter_id,
                "success_count": success_count,
                "saved_count": saved_count,
                "total_count": total_count,
            }
        )

    background_tasks.add_task(process_chapter)

    return {"message": "Chapter translation started", "page_count": len(image_files)}


class PageTranslateRequest(BaseModel):
    manga_id: str
    chapter_id: str
    image_name: str
    source_language: Optional[str] = None  # 默认从 settings 获取
    target_language: Optional[str] = None  # 默认从 settings 获取


@router.post("/page", response_model=TranslateImageResponse)
async def retranslate_page(
    request: PageTranslateRequest,
    pipeline: Pipeline = Depends(get_pipeline),
    settings=Depends(get_settings),
):
    """
    Re-translate a specific page.
    """
    # Resolve manga path (logic duplicated from manga.py for now to avoid circular deps)
    data_dir = Path(settings.data_dir)
    direct_path = data_dir / request.manga_id
    if direct_path.exists():
        manga_path = direct_path
    else:
        raw_path = data_dir / "raw" / request.manga_id
        if raw_path.exists():
            manga_path = raw_path
        else:
            manga_path = direct_path

    image_path = manga_path / request.chapter_id / request.image_name

    if not image_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Image not found: {image_path}",
        )

    # 使用 request 中的语言，如果为 None 则从 settings 获取
    source_lang = request.source_language or settings.source_language
    target_lang = request.target_language or settings.target_language

    context = TaskContext(
        image_path=str(image_path),
        source_language=source_lang,
        target_language=target_lang,
    )

    # Set specific output path to overwrite existing
    output_base = Path(settings.output_dir) / request.manga_id / request.chapter_id
    output_base.mkdir(parents=True, exist_ok=True)
    context.output_path = str(output_base / request.image_name)

    # Process through pipeline with callback
    result = await pipeline.process(context, status_callback=pipeline_status_callback)

    _tasks[result.task.task_id] = result.task

    # Notify completion
    await broadcast_event(
        {
            "type": "page_complete",
            "manga_id": request.manga_id,
            "chapter_id": request.chapter_id,
            "image_name": request.image_name,
            "url": f"/output/{request.manga_id}/{request.chapter_id}/{request.image_name}?t={asyncio.get_running_loop().time()}",
        }
    )

    return TranslateImageResponse(
        task_id=result.task.task_id,
        status=result.task.status,
        output_path=result.task.output_path,
        regions_count=len(result.task.regions),
    )


@router.get("/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: UUID):
    """
    Get the status of a translation task.
    """
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Task not found: {task_id}"
        )

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress=1.0 if task.status == TaskStatus.COMPLETED else 0.5,
        output_path=task.output_path,
        error_message=task.error_message,
    )
