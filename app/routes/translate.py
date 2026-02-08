"""
Translation API Routes.

Provides endpoints for image translation operations.
"""

from pathlib import Path
from typing import Dict, Set, Optional
from uuid import UUID
import logging

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
logger = logging.getLogger(__name__)

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


def _build_pipeline_error_detail(result, fallback_message: str) -> dict:
    task = result.task
    return {
        "code": task.error_code or "pipeline_failed",
        "message": task.error_message or fallback_message,
        "task_id": str(task.task_id),
        "status": task.status.value,
        "output_path": task.output_path,
    }


def _pipeline_failure_status_code(result) -> int:
    if getattr(result.task, "error_code", None) == "ocr_no_text":
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    return status.HTTP_500_INTERNAL_SERVER_ERROR


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
    if not result.success:
        raise HTTPException(
            status_code=_pipeline_failure_status_code(result),
            detail=_build_pipeline_error_detail(result, "Image translation failed"),
        )
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
        total_count = 0
        # 使用 request 中的语言，如果为 None 则从 settings 获取
        try:
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

            total_count = len(contexts)
            await broadcast_event(
                {
                    "type": "chapter_start",
                    "manga_id": request.manga_id,
                    "chapter_id": request.chapter_id,
                    "total_pages": total_count,
                }
            )

            results = await pipeline.process_batch(
                contexts, status_callback=pipeline_status_callback
            )

            from app.services.page_status import find_translated_file

            saved_count = 0
            effective_success_count = 0
            pipeline_success_count = 0
            failed_translation_count = 0
            failed_pipeline_count = 0
            failed_ocr_empty_count = 0

            for img_path, result in zip(image_files, results):
                translated_file = find_translated_file(output_base, img_path.stem)
                has_output_file = bool(translated_file)
                if has_output_file:
                    saved_count += 1

                if result.success:
                    pipeline_success_count += 1

                regions_count = len(result.task.regions or [])
                if regions_count == 0:
                    failed_ocr_empty_count += 1

                has_failure_marker = any(
                    (region.target_text or "").strip().startswith("[翻译失败]")
                    for region in (result.task.regions or [])
                )
                if has_failure_marker:
                    failed_translation_count += 1

                is_effective_success = (
                    result.success
                    and has_output_file
                    and not has_failure_marker
                    and regions_count > 0
                )
                if is_effective_success:
                    effective_success_count += 1
                elif not result.success:
                    failed_pipeline_count += 1

            failed_count = total_count - effective_success_count
            final_status = (
                "error"
                if effective_success_count == 0
                else "partial" if failed_count > 0 else "success"
            )

            await broadcast_event(
                {
                    "type": "chapter_complete",
                    "manga_id": request.manga_id,
                    "chapter_id": request.chapter_id,
                    "status": final_status,
                    # success_count for frontend should represent effective success
                    # (pipeline success + output exists + no explicit failure marker).
                    "success_count": effective_success_count,
                    "pipeline_success_count": pipeline_success_count,
                    "failed_pipeline_count": failed_pipeline_count,
                    "failed_translation_count": failed_translation_count,
                    "failed_ocr_empty_count": failed_ocr_empty_count,
                    "failed_count": failed_count,
                    "saved_count": saved_count,
                    "total_count": total_count,
                }
            )
        except Exception as exc:
            logger.exception(
                "[%s/%s] chapter translation background task failed",
                request.manga_id,
                request.chapter_id,
            )
            await broadcast_event(
                {
                    "type": "chapter_complete",
                    "manga_id": request.manga_id,
                    "chapter_id": request.chapter_id,
                    "status": "error",
                    "success_count": 0,
                    "failed_count": total_count or len(image_files),
                    "failed_ocr_empty_count": 0,
                    "saved_count": 0,
                    "total_count": total_count or len(image_files),
                    "error_message": str(exc),
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
    if not result.success:
        await broadcast_event(
            {
                "type": "page_failed",
                "manga_id": request.manga_id,
                "chapter_id": request.chapter_id,
                "image_name": request.image_name,
                "error_message": result.task.error_message or "Page translation failed",
            }
        )
        raise HTTPException(
            status_code=_pipeline_failure_status_code(result),
            detail=_build_pipeline_error_detail(result, "Page translation failed"),
        )

    # Notify completion
    translated_name = Path(result.task.output_path).name if result.task.output_path else request.image_name
    await broadcast_event(
        {
            "type": "page_complete",
            "manga_id": request.manga_id,
            "chapter_id": request.chapter_id,
            "image_name": request.image_name,
            "url": f"/output/{request.manga_id}/{request.chapter_id}/{translated_name}?t={asyncio.get_running_loop().time()}",
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
