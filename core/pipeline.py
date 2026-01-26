"""
Pipeline Manager - Orchestrates the translation pipeline.

Chains all processing modules together:
OCR → Translator → Inpainter → Renderer

Includes performance metrics collection for each stage.
"""

import asyncio
import logging
import os
import sys
import time
import contextlib
from typing import Optional

from .models import PipelineResult, TaskContext, TaskStatus
from .metrics import PipelineMetrics, StageMetrics, Timer, start_metrics
from .modules import (
    BaseModule,
    InpainterModule,
    OCRModule,
    RendererModule,
    TranslatorModule,
)

# 配置日志
logger = logging.getLogger(__name__)


@contextlib.contextmanager
def suppress_native_stderr():
    """在 OS 级别抑制 stderr（包括 C/ObjC 的 NSLog）"""
    try:
        stderr_fd = sys.stderr.fileno()
        saved_stderr = os.dup(stderr_fd)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stderr_fd)
        os.close(devnull)
        try:
            yield
        finally:
            os.dup2(saved_stderr, stderr_fd)
            os.close(saved_stderr)
    except (ValueError, OSError):
        # 如果无法获取文件描述符（如在某些环境中），直接跳过
        yield


class Pipeline:
    """
    Translation pipeline manager.
    
    Orchestrates the flow of data through all processing stages.
    Each stage updates the TaskContext with its results.
    
    流程: OCR → Translator → Inpainter → Renderer
    """

    def __init__(
        self,
        ocr: Optional[BaseModule] = None,
        translator: Optional[BaseModule] = None,
        inpainter: Optional[BaseModule] = None,
        renderer: Optional[BaseModule] = None,
    ):
        """
        Initialize pipeline with modules.
        
        Args:
            ocr: OCR module (default: OCRModule) - includes detection
            translator: Translation module (default: TranslatorModule)
            inpainter: Inpainting module (default: InpainterModule)
            renderer: Rendering module (default: RendererModule)
        """
        self.ocr = ocr or OCRModule()
        self.translator = translator or TranslatorModule()
        self.inpainter = inpainter or InpainterModule()
        self.renderer = renderer or RendererModule()

        self.stages = [
            ("ocr", self.ocr),
            ("translator", self.translator),
            ("inpainter", self.inpainter),
            ("renderer", self.renderer),
        ]

    async def process(
        self, 
        context: TaskContext,
        collect_metrics: bool = True,
        status_callback: Optional[callable] = None,
    ) -> PipelineResult:
        """
        Run the full translation pipeline.
        
        Args:
            context: Initial task context with image_path
            collect_metrics: Whether to collect performance metrics
            status_callback: Optional callable(stage_name, status, task_id)
            
        Returns:
            PipelineResult with success status and final context
        """
        start_time = time.time()
        stages_completed = []
        
        # Initialize metrics
        metrics = PipelineMetrics() if collect_metrics else None
        stage_timings = {}

        logger.info(f"[{context.task_id}] Pipeline 开始: {context.image_path}")

        try:
            context.update_status(TaskStatus.PROCESSING)
            if status_callback:
                await status_callback("init", TaskStatus.PROCESSING, context.task_id)

            for stage_name, module in self.stages:
                stage_start = time.perf_counter()
                
                try:
                    # 使用 stderr 抑制器消除 NSLog 输出
                    with suppress_native_stderr():
                        context = await module.process(context)
                except Exception as stage_error:
                    logger.error(f"[{context.task_id}] {stage_name} 阶段失败: {stage_error}")
                    raise
                
                stage_duration = (time.perf_counter() - stage_start) * 1000
                stage_timings[stage_name] = stage_duration
                stages_completed.append(stage_name)
                
                if status_callback:
                    await status_callback(stage_name, TaskStatus.PROCESSING, context.task_id)

                if metrics:
                    # Get sub-metrics from module if available
                    sub_metrics = {}
                    if hasattr(module, 'last_metrics'):
                        sub_metrics = module.last_metrics or {}
                    
                    metrics.add_stage(StageMetrics(
                        name=stage_name,
                        duration_ms=stage_duration,
                        items_processed=len(context.regions) if context.regions else 0,
                        sub_metrics=sub_metrics,
                    ))

            context.update_status(TaskStatus.COMPLETED)
            if status_callback:
                await status_callback("complete", TaskStatus.COMPLETED, context.task_id)
            
            total_time = (time.time() - start_time) * 1000
            if metrics:
                metrics.total_duration_ms = total_time
            
            logger.info(f"[{context.task_id}] Pipeline 完成: 耗时 {total_time:.0f}ms, 输出 {context.output_path}")
            
            result = PipelineResult(
                success=True,
                task=context,
                processing_time_ms=total_time,
                stages_completed=stages_completed,
            )
            
            # Attach metrics to result
            if metrics:
                result.metrics = metrics
            
            return result

        except Exception as e:
            logger.error(f"[{context.task_id}] Pipeline 失败: {e}")
            context.update_status(TaskStatus.FAILED, error=str(e))
            if status_callback:
                await status_callback("failed", TaskStatus.FAILED, context.task_id)
            
            total_time = (time.time() - start_time) * 1000
            if metrics:
                metrics.total_duration_ms = total_time
            
            result = PipelineResult(
                success=False,
                task=context,
                processing_time_ms=total_time,
                stages_completed=stages_completed,
            )
            
            if metrics:
                result.metrics = metrics
            
            return result

    async def process_batch(
        self,
        contexts: list[TaskContext],
        max_concurrent: int = 5,
        status_callback: Optional[callable] = None,
    ) -> list[PipelineResult]:
        """
        Process multiple images concurrently.
        
        Args:
            contexts: List of task contexts to process
            max_concurrent: Maximum concurrent tasks
            
        Returns:
            List of pipeline results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(ctx: TaskContext) -> PipelineResult:
            async with semaphore:
                return await self.process(ctx, status_callback=status_callback)

        tasks = [process_with_semaphore(ctx) for ctx in contexts]
        return await asyncio.gather(*tasks)


# Convenience function
async def translate_image(
    image_path: str,
    source_lang: str = "en",
    target_lang: str = "zh-CN",
    verbose: bool = False,
) -> PipelineResult:
    """
    Translate a single image.
    
    Args:
        image_path: Path to source image
        source_lang: Source language code
        target_lang: Target language code
        verbose: Print performance metrics
        
    Returns:
        PipelineResult with translation outcome
    """
    pipeline = Pipeline()
    context = TaskContext(
        image_path=image_path,
        source_language=source_lang,
        target_language=target_lang,
    )
    result = await pipeline.process(context)
    
    if verbose and hasattr(result, 'metrics') and result.metrics:
        print(result.metrics.summary())
    
    return result
